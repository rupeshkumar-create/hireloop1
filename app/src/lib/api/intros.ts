/**
 * Intro requests API client — wraps GET /api/v1/intros and the cancel action.
 *
 * Mirrors the profile-cache pattern (see profile.ts): the dashboard keys its
 * panels by id, so the Inbox panel fully remounts every time it's reopened.
 * Without a cache that's a fresh /intros round-trip — and a skeleton flash —
 * on every open. We keep the last successful payload in module scope so
 * reopening is instant, and de-dupe concurrent in-flight requests so the Home
 * and Inbox panels mounting together share one network call.
 */

import { apiFetch } from "@/lib/api/client";

/** Who initiated the intro — drives the candidate-side UI (respond vs cancel). */
export type IntroDirection =
  | "candidate_to_hm"
  | "candidate_to_recruiter"
  | "recruiter_to_candidate";

export type IntroRequest = {
  id: string;
  job_id: string;
  status: string;
  direction?: IntroDirection;
  job_title: string;
  company_name: string | null;
  hm_name: string | null;
  hm_title?: string | null;
  created_at: string;
  sent_at?: string | null;
  opened_at?: string | null;
  replied_at: string | null;
  followup_ready?: boolean;
  thankyou_ready?: boolean;
  thankyou_sent?: boolean;
  nudged_at?: string | null;
};

export type IntroDetail = IntroRequest & {
  draft_email: string | null;
  error_message: string | null;
  gmail_connected: boolean;
  hm_email?: string | null;
  followup_draft_email?: string | null;
  followup_draft_at?: string | null;
  thankyou_draft_email?: string | null;
  thankyou_draft_at?: string | null;
  thankyou_sent_at?: string | null;
  gmail_thread_id?: string | null;
};

export type OutboundDraft = {
  subject?: string;
  body_html?: string;
  body_text?: string;
};

export type CreateIntroResult = {
  intro_id?: string;
  status?: string;
  direction?: IntroDirection;
  message?: string;
};

let _introsCache: IntroRequest[] | null = null;
let _introsInFlight: Promise<IntroRequest[]> | null = null;

/** Last successfully fetched intros, or null if none cached yet. Synchronous. */
export function getCachedIntros(): IntroRequest[] | null {
  return _introsCache;
}

/** Drop the cache — call after a mutation so the next read revalidates. */
export function invalidateIntrosCache(): void {
  _introsCache = null;
}

/**
 * Fetch the current user's intro requests.
 *
 * @param opts.force  Bypass the in-flight de-dupe and force a fresh request
 *                    (the result still refreshes the cache).
 */
export async function fetchIntros(
  opts: { force?: boolean } = {}
): Promise<IntroRequest[]> {
  if (!opts.force && _introsInFlight) return _introsInFlight;

  const req = apiFetch<IntroRequest[]>("/api/v1/intros")
    .then((data) => {
      _introsCache = data;
      return data;
    })
    .finally(() => {
      if (_introsInFlight === req) _introsInFlight = null;
    });

  _introsInFlight = req;
  return req;
}

/** Create an intro request for a job through the API service layer. */
export async function createCandidateIntro(jobId: string): Promise<CreateIntroResult> {
  const result = await apiFetch<CreateIntroResult>("/api/v1/intros", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
  _introsCache = null;
  return result;
}

/**
 * Cancel a pending intro. Optimistically patches the cache so a subsequent
 * panel reopen reflects the new status without waiting for a refetch.
 */
/** Candidate confirms the HM replied — closes the intro funnel measurably. */
export async function markIntroReplied(introId: string): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/mark-replied`, { method: "POST" });
  _introsCache = null;
}

export async function cancelIntro(introId: string): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/cancel`, { method: "POST" });
  if (_introsCache) {
    _introsCache = _introsCache.map((i) =>
      i.id === introId ? { ...i, status: "cancelled" } : i
    );
  }
}

/**
 * Accept or decline a recruiter→candidate intro request. Optimistically
 * patches the cache so a panel reopen reflects the new status immediately.
 */
export async function respondToIntro(
  introId: string,
  accept: boolean
): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/respond?accept=${accept}`, {
    method: "POST",
  });
  const next = accept ? "accepted" : "declined";
  if (_introsCache) {
    _introsCache = _introsCache.map((i) =>
      i.id === introId ? { ...i, status: next } : i
    );
  }
}

/** Full intro detail including Nitya draft email preview. */
export async function fetchIntroDetail(introId: string): Promise<IntroDetail> {
  return apiFetch<IntroDetail>(`/api/v1/intros/${introId}`);
}

/** Candidate approves the draft and sends via their connected Gmail. */
export async function approveIntroSend(introId: string): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/approve-send`, { method: "POST" });
  if (_introsCache) {
    _introsCache = _introsCache.map((i) =>
      i.id === introId ? { ...i, status: "sent" } : i
    );
  }
}

export async function patchFollowupDraft(
  introId: string,
  draft: OutboundDraft
): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/followup-draft`, {
    method: "PATCH",
    body: JSON.stringify(draft),
  });
}

export async function approveFollowupSend(introId: string): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/approve-send-followup`, {
    method: "POST",
  });
  _introsCache = null;
}

export async function createThankyouDraft(introId: string): Promise<OutboundDraft | null> {
  const res = await apiFetch<{ thankyou_draft_email: OutboundDraft | null }>(
    `/api/v1/intros/${introId}/thankyou-draft`,
    { method: "POST" }
  );
  _introsCache = null;
  return res.thankyou_draft_email;
}

export async function patchThankyouDraft(
  introId: string,
  draft: OutboundDraft
): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/thankyou-draft`, {
    method: "PATCH",
    body: JSON.stringify(draft),
  });
}

export async function approveThankyouSend(introId: string): Promise<void> {
  await apiFetch(`/api/v1/intros/${introId}/approve-send-thankyou`, {
    method: "POST",
  });
  _introsCache = null;
}
