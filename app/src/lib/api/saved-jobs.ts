import { apiAuthFetch } from "@/lib/api/auth-fetch";
import type { MatchedJob } from "@/lib/api/matches";

type SavedJobsListener = () => void;

const savedJobsListeners = new Set<SavedJobsListener>();

/** Subscribe to saved-job mutations (save/unsave). Returns an unsubscribe fn. */
export function subscribeSavedJobs(listener: SavedJobsListener): () => void {
  savedJobsListeners.add(listener);
  return () => {
    savedJobsListeners.delete(listener);
  };
}

function notifySavedJobsChanged(): void {
  for (const listener of savedJobsListeners) {
    listener();
  }
}

export { notifySavedJobsChanged };

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
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Could not save job: ${res.status}`
    );
  }
  notifySavedJobsChanged();
}

export async function unsaveJob(jobId: string): Promise<void> {
  const res = await apiAuthFetch(`/api/v1/me/saved-jobs/${jobId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Could not remove saved job: ${res.status}`
    );
  }
  notifySavedJobsChanged();
}
