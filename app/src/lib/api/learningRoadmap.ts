/**
 * Learning roadmap API.
 *
 * Per-job AI upskilling plan, generated from the candidate's resume + the job
 * description and rendered as a self-contained interactive HTML app.
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  parseReadyOrAccepted,
  type ReadyOrAccepted,
} from "@/lib/api/aiOperations";

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

export type LearningRoadmapReady = {
  status: "ready";
  roadmap_id: string;
  download_path?: string;
  message?: string;
};

export async function requestLearningRoadmap(
  jobId: string,
): Promise<ReadyOrAccepted<LearningRoadmapReady>> {
  const res = await apiAuthFetch("/api/v1/learning-roadmaps/roadmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId }),
  });
  return parseReadyOrAccepted(res, (body) => {
    const data = body as {
      status?: string;
      roadmap_id?: string;
      download_path?: string;
      message?: string;
    };
    if (data.status === "ready" && data.roadmap_id) {
      return {
        status: "ready",
        roadmap_id: data.roadmap_id,
        download_path: data.download_path,
        message: data.message,
      };
    }
    // Some ready payloads only include download_path.
    if (data.status === "ready" && data.download_path) {
      const id = data.download_path.split("/").filter(Boolean).pop();
      if (id) {
        return {
          status: "ready",
          roadmap_id: id,
          download_path: data.download_path,
          message: data.message,
        };
      }
    }
    throw new Error(data.message?.trim() || "Learning roadmap was not ready.");
  });
}

export async function getLearningRoadmap(roadmapId: string): Promise<LearningRoadmapRow> {
  const res = await apiAuthFetch(`/api/v1/learning-roadmaps/${roadmapId}`);
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
  return res.json() as Promise<LearningRoadmapRow>;
}

/** @deprecated Prefer AiOperationsProvider tracking after requestLearningRoadmap. */
export async function pollLearningRoadmap(
  roadmapId: string,
  maxAttempts = 20,
  intervalMs = 2000,
): Promise<LearningRoadmapRow> {
  for (let i = 0; i < maxAttempts; i++) {
    const data = await getLearningRoadmap(roadmapId);
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
