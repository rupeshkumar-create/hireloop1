/**
 * Onboarding profile-source helpers. LinkedIn sign-in (OIDC) only returns
 * name/email/photo — never work history — so we collect the profile separately:
 * a LinkedIn profile URL (triggers the Apify scrape) or a CV upload (LLM parse).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";

const LINKEDIN_IN_RE = /linkedin\.com\/in\/[^/?#\s]+/i;

export function isValidLinkedInUrl(url: string): boolean {
  return LINKEDIN_IN_RE.test(url.trim());
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

/** Upload a CV, apply the parsed fields to the profile, and return the parse
 *  summary so onboarding can show "here's what I found" for confirmation. */
export async function uploadResumeAndApply(file: File): Promise<ParsedResumeSummary> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiAuthFetch("/api/v1/resumes/upload", {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Resume upload failed");
  }
  const data = (await res.json()) as {
    resume_id: string;
    parsed?: ParsedResumeSummary;
  };
  // Apply parsed fields to the profile (best-effort — don't fail activation).
  try {
    await apiAuthFetch(`/api/v1/resumes/${data.resume_id}/apply-to-profile`, {
      method: "POST",
    });
  } catch {
    /* non-fatal */
  }
  return data.parsed ?? {};
}
