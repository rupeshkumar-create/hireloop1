/**
 * Onboarding profile-source helpers. LinkedIn sign-in (OIDC) only returns
 * name/email/photo — never work history — so we collect the profile separately:
 * a LinkedIn profile URL (triggers the Apify scrape) or a CV upload (LLM parse).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { invalidateMatchFeedCache } from "@/lib/api/matches";

const LINKEDIN_IN_RE = /linkedin\.com\/in\/[^/?#\s]+/i;
const RESUME_PARSE_POLL_MS = 2000;
const RESUME_PARSE_TIMEOUT_MS = 120_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function isValidLinkedInUrl(url: string): boolean {
  return LINKEDIN_IN_RE.test(url.trim());
}

/** LinkedIn vanity slug from a profile URL, e.g. `rupesh-kumar`. */
export function linkedInProfileId(url: string | null | undefined): string | null {
  if (!url?.trim()) return null;
  const match = url.trim().match(/linkedin\.com\/in\/([^/?#\s]+)/i);
  return match?.[1] ?? null;
}

/** Save the LinkedIn profile URL; the server enriches via Apify/LinkDAPI. */
export async function saveLinkedInUrl(url: string): Promise<void> {
  const res = await apiAuthFetch("/api/v1/me/linkedin", {
    method: "POST",
    body: JSON.stringify({ linkedin_url: url.trim() }),
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

type ResumeUploadPayload = {
  resume_id: string;
  parsed?: ParsedResumeSummary;
  parse_status?: "pending" | "ready" | "failed";
  message?: string;
};

type ResumeStatusPayload = {
  parse_status: "pending" | "ready" | "failed";
  parsed?: ParsedResumeSummary;
  message?: string | null;
};

async function waitForResumeParse(resumeId: string): Promise<ParsedResumeSummary> {
  const deadline = Date.now() + RESUME_PARSE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const res = await apiAuthFetch(`/api/v1/resumes/${resumeId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(
        (err as { detail?: string }).detail ?? "Couldn't check CV parsing status",
      );
    }
    const data = (await res.json()) as ResumeStatusPayload;
    if (data.parse_status === "ready") {
      return data.parsed ?? {};
    }
    if (data.parse_status === "failed") {
      throw new Error(data.message ?? "Couldn't read that file. Try another CV.");
    }
    await sleep(RESUME_PARSE_POLL_MS);
  }
  throw new Error(
    "CV parsing is taking longer than expected. Please try uploading again.",
  );
}

/** Upload a CV, apply the parsed fields to the profile, and return the parse summary. */
export async function uploadResumeAndApply(file: File): Promise<ParsedResumeSummary> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiAuthFetch("/api/v1/resumes/upload", {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
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
    throw new Error(detail ?? "Resume upload failed");
  }
  const data = (await res.json()) as ResumeUploadPayload;
  const parsed =
    data.parse_status === "pending"
      ? await waitForResumeParse(data.resume_id)
      : (data.parsed ?? {});

  // Apply parsed fields to the profile (best-effort — don't fail activation).
  // replace: the fresh CV wins over any earlier LinkedIn enrichment; the
  // candidate reviews and corrects everything on the next screen anyway.
  const applyRes = await apiAuthFetch(
    `/api/v1/resumes/${data.resume_id}/apply-to-profile?mode=replace`,
    { method: "POST" },
  );
  if (!applyRes.ok && applyRes.status !== 409) {
    // Resume is stored — profile apply can be retried from dashboard.
  }
  invalidateMatchFeedCache();
  return parsed;
}
