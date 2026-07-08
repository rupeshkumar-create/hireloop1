/**
 * Learning roadmap API.
 *
 * Per-job AI upskilling plan, generated from the candidate's resume + the job
 * description and rendered as a self-contained interactive HTML app.
 * Mirrors the tailored-resume request → poll → open flow.
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type LearningRoadmapRow = {
  id: string;
  job_id?: string;
  status: string;
  summary_line: string | null;
  job_title?: string;
  created_at?: string;
  expires_at?: string;
  download_url?: string;
};

export async function requestLearningRoadmap(
  jobId: string
): Promise<{ status: string; roadmap_id?: string; download_path?: string; message?: string }> {
  const res = await apiAuthFetch("/api/v1/learning-roadmaps/roadmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(async () => ({
      detail: (await res.text().catch(() => "")) || res.statusText,
    }));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail?.trim() || `Roadmap failed: ${res.status}`);
  }
  return res.json();
}

export async function pollLearningRoadmap(
  roadmapId: string,
  maxAttempts = 20,
  intervalMs = 2000
): Promise<LearningRoadmapRow> {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await apiAuthFetch(`/api/v1/learning-roadmaps/${roadmapId}`);
    if (!res.ok) throw new Error(`Poll failed: ${res.status}`);
    const data = (await res.json()) as LearningRoadmapRow;
    if (data.status === "ready") return data;
    if (data.status === "failed") throw new Error("Roadmap generation failed");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("Roadmap timed out — try again in a moment");
}

export async function listLearningRoadmaps(): Promise<LearningRoadmapRow[]> {
  const res = await apiAuthFetch("/api/v1/learning-roadmaps/roadmaps");
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  return res.json();
}

/**
 * Open the roadmap app in a new tab. The download endpoint is auth-protected,
 * so we fetch with the bearer token attached and open via a blob URL (a bare
 * window.open would 401).
 */
export async function openLearningRoadmap(roadmapId: string): Promise<void> {
  const res = await apiAuthFetch(`/api/v1/learning-roadmaps/${roadmapId}/download`);
  if (!res.ok) throw new Error(`Open failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
