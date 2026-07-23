/**
 * Onboarding profile-source helpers. LinkedIn sign-in (OIDC) only returns
 * name/email/photo — never work history — so we collect the profile separately:
 * a LinkedIn profile URL (triggers the Apify scrape) or a CV upload (LLM parse).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  parseReadyOrAccepted,
  type ReadyOrAccepted,
} from "@/lib/api/aiOperations";
import { invalidateMatchFeedCache } from "@/lib/api/matches";

/** LinkedIn vanity slug from a profile URL, e.g. `rupesh-kumar`. */
export function linkedInProfileId(url: string | null | undefined): string | null {
  if (!url?.trim()) return null;
  const raw = url.trim();
  const fromHost = raw.match(/linkedin\.com\/in\/([^/?#\s]+)/i);
  if (fromHost?.[1]) {
    try {
      return decodeURIComponent(fromHost[1]).replace(/\/+$/, "") || null;
    } catch {
      return fromHost[1].replace(/\/+$/, "") || null;
    }
  }
  if (raw.startsWith("in/")) {
    const slug = raw.slice(3).split(/[/?#]/)[0]?.replace(/\/+$/, "");
    return slug || null;
  }
  // Allow paste of just the vanity slug (no host).
  if (/^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,98}[a-zA-Z0-9])?$/.test(raw)) {
    return raw;
  }
  return null;
}

export function normalizeLinkedInUrl(url: string): string | null {
  const id = linkedInProfileId(url);
  if (!id) return null;
  return `https://www.linkedin.com/in/${id}`;
}

export function isValidLinkedInUrl(url: string): boolean {
  return Boolean(normalizeLinkedInUrl(url));
}

/** Save the LinkedIn profile URL; the server enriches via Apify/LinkDAPI. */
export async function saveLinkedInUrl(url: string): Promise<void> {
  const normalized = normalizeLinkedInUrl(url);
  if (!normalized) {
    throw new Error("Enter a valid LinkedIn URL (linkedin.com/in/your-name)");
  }
  const res = await apiAuthFetch("/api/v1/me/linkedin", {
    method: "POST",
    body: JSON.stringify({ linkedin_url: normalized }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? "Couldn't save your LinkedIn URL"
    );
  }
}

/** What the CV parser pulled out — shown back to the candidate to confirm. */
export type ParsedResumeSummary = {
  full_name?: string | null;
  current_title?: string | null;
  current_company?: string | null;
  years_experience?: number | null;
  skills?: string[];
};

export type ResumeUploadReady = {
  resume_id: string;
  parsed: ParsedResumeSummary;
  parse_status?: "pending" | "ready" | "failed";
  message?: string;
};

type ResumeStatusPayload = {
  parse_status: "pending" | "ready" | "failed";
  parsed?: ParsedResumeSummary;
  message?: string | null;
};

export async function fetchResumeParseStatus(
  resumeId: string,
): Promise<ResumeStatusPayload> {
  const res = await apiAuthFetch(`/api/v1/resumes/${resumeId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? "Couldn't check CV parsing status",
    );
  }
  return res.json() as Promise<ResumeStatusPayload>;
}

export async function applyResumeToProfile(resumeId: string): Promise<void> {
  const applyRes = await apiAuthFetch(
    `/api/v1/resumes/${resumeId}/apply-to-profile?mode=replace`,
    { method: "POST" },
  );
  if (!applyRes.ok && applyRes.status !== 409) {
    // Resume is stored — profile apply can be retried from dashboard.
  }
  invalidateMatchFeedCache();
}

/**
 * Upload a CV. Returns parsed fields immediately when available, otherwise an
 * AiOperationAccepted for durable parse tracking.
 */
export async function uploadResume(
  file: File,
): Promise<ReadyOrAccepted<ResumeUploadReady>> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiAuthFetch("/api/v1/resumes/upload", {
    method: "POST",
    body: fd,
  });
  if (!res.ok && res.status !== 202) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail;
    if (res.status === 401) {
      throw new Error(detail ?? "Session expired. Sign out and sign in again.");
    }
    if (res.status === 502 || res.status === 503) {
      throw new Error(
        detail ??
          "API is temporarily unavailable. Check NEXT_PUBLIC_API_URL on Vercel and redeploy.",
      );
    }
    // Fall through to parseReadyOrAccepted for structured errors / 202.
  }
  return parseReadyOrAccepted(res, (body) => {
    const data = body as ResumeUploadReady;
    if (!data?.resume_id) {
      throw new Error("Resume upload did not return a resume id.");
    }
    return {
      resume_id: data.resume_id,
      parsed: data.parsed ?? {},
      parse_status: data.parse_status,
      message: data.message,
    };
  });
}

/**
 * Upload a CV, wait for parse via the shared operation manager when needed,
 * apply parsed fields to the profile, and return the parse summary.
 */
export async function uploadResumeAndApply(
  file: File,
  waitForOperation: (
    accepted: import("@/lib/api/aiOperations").AiOperationAccepted,
  ) => Promise<import("@/lib/api/aiOperations").AiOperationResponse>,
): Promise<ParsedResumeSummary> {
  const outcome = await uploadResume(file);

  let resumeId: string;
  let parsed: ParsedResumeSummary;

  if (outcome.status === "ready") {
    resumeId = outcome.data.resume_id;
    if (outcome.data.parse_status === "ready" || outcome.data.parsed) {
      parsed = outcome.data.parsed ?? {};
    } else {
      const status = await fetchResumeParseStatus(resumeId);
      if (status.parse_status === "failed") {
        throw new Error(status.message ?? "Couldn't read that file. Try another CV.");
      }
      parsed = status.parsed ?? {};
    }
  } else {
    const terminal = await waitForOperation(outcome.operation);
    if (terminal.status !== "succeeded" || !terminal.result_id) {
      throw new Error(
        terminal.error_message?.trim() ||
          terminal.message.trim() ||
          "Couldn't read that file. Try another CV.",
      );
    }
    resumeId = terminal.result_id;
    const status = await fetchResumeParseStatus(resumeId);
    if (status.parse_status === "failed") {
      throw new Error(status.message ?? "Couldn't read that file. Try another CV.");
    }
    parsed = status.parsed ?? {};
  }

  await applyResumeToProfile(resumeId);
  return parsed;
}
