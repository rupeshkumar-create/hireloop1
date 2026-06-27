/**
 * Tailored resume API (P20)
 */

import { getApiBaseUrl } from "@/lib/api/base-url";
import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type TailorTemplate = "modern" | "classic" | "minimal";

export type TailoredResumeRow = {
  id: string;
  job_id: string;
  template: string;
  status: string;
  summary_line: string | null;
  job_title?: string;
  created_at: string;
  expires_at: string;
  download_url?: string;
};

export async function requestTailoredResume(
  jobId: string,
  template: TailorTemplate = "modern"
): Promise<{ status: string; resume_id?: string; download_path?: string; message?: string }> {
  const res = await apiAuthFetch("/api/v1/tailored-resumes/tailor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, template }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `Tailor failed: ${res.status}`);
  }
  return res.json();
}

export async function pollTailoredResume(
  resumeId: string,
  maxAttempts = 15,
  intervalMs = 2000
): Promise<TailoredResumeRow> {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await apiAuthFetch(`/api/v1/tailored-resumes/tailored/${resumeId}`);
    if (!res.ok) throw new Error(`Poll failed: ${res.status}`);
    const data = (await res.json()) as TailoredResumeRow;
    if (data.status === "ready") return data;
    if (data.status === "failed") throw new Error("Tailoring failed");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Tailoring timed out — try again in a moment");
}

export async function listTailoredResumes(): Promise<TailoredResumeRow[]> {
  const res = await apiAuthFetch("/api/v1/tailored-resumes/tailored");
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  return res.json();
}

export function openTailoredDownload(resumeId: string) {
  const url = `${getApiBaseUrl()}/api/v1/tailored-resumes/tailored/${resumeId}/download`;
  window.open(url, "_blank", "noopener,noreferrer");
}

/**
 * Fetch the rendered resume HTML for in-app preview (no auto-print dialog).
 * Goes through apiAuthFetch so the bearer token is attached — the endpoint is
 * auth-protected, so a bare window.open / iframe src would 401.
 */
export async function fetchTailoredResumeHtml(resumeId: string): Promise<string> {
  const res = await apiAuthFetch(
    `/api/v1/tailored-resumes/tailored/${resumeId}/download?print_dialog=false`
  );
  if (!res.ok) throw new Error(`Preview failed: ${res.status}`);
  return res.text();
}

/**
 * Authenticated download — opens the print-ready resume in a new tab with the
 * bearer token attached (via a blob URL), unlike the bare openTailoredDownload.
 */
export async function downloadTailoredResume(resumeId: string): Promise<void> {
  const res = await apiAuthFetch(
    `/api/v1/tailored-resumes/tailored/${resumeId}/download`
  );
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  // Revoke after the new tab has had time to load the document.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
