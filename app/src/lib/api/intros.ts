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

/**
 * Cancel a pending intro. Optimistically patches the cache so a subsequent
 * panel reopen reflects the new status without waiting for a refetch.
 */
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
