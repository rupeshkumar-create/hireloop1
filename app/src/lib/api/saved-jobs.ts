import { apiAuthFetch } from "@/lib/api/auth-fetch";
import type { MatchedJob } from "@/lib/api/matches";

export async function fetchSavedJobs(): Promise<MatchedJob[]> {
  const res = await apiAuthFetch("/api/v1/me/saved-jobs", { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Saved jobs failed: ${res.status}`
    );
  }
  return res.json();
}

export async function fetchSavedJobIds(): Promise<Set<string>> {
  const res = await apiAuthFetch("/api/v1/me/saved-jobs/ids", { cache: "no-store" });
  if (!res.ok) return new Set();
  const data = (await res.json()) as { job_ids?: string[] };
  return new Set(data.job_ids ?? []);
}

export async function saveJob(jobId: string): Promise<void> {
  const res = await apiAuthFetch(`/api/v1/me/saved-jobs/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Could not save job: ${res.status}`
    );
  }
}

export async function unsaveJob(jobId: string): Promise<void> {
  const res = await apiAuthFetch(`/api/v1/me/saved-jobs/${jobId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Could not remove saved job: ${res.status}`
    );
  }
}
