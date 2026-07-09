import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { notifySavedJobsChanged } from "@/lib/api/saved-jobs";

type PipelineListener = () => void;

const pipelineListeners = new Set<PipelineListener>();

export function subscribeJobPipeline(listener: PipelineListener): () => void {
  pipelineListeners.add(listener);
  return () => {
    pipelineListeners.delete(listener);
  };
}

function notifyJobPipelineChanged(): void {
  for (const listener of pipelineListeners) {
    listener();
  }
}

export type JobApplicationRecord = {
  application_id: string;
  job_id: string;
  saved: boolean;
  applied: boolean;
  status: string;
};

export async function recordJobOutcome(
  jobId: string,
  stage: string,
  notes?: string,
): Promise<void> {
  const res = await apiAuthFetch(`/api/v1/me/jobs/${jobId}/outcome`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage, notes: notes ?? null }),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Could not save outcome: ${res.status}`,
    );
  }
}

/** Log a direct application and bookmark the job for the tracker. */
export async function recordJobApplication(
  jobId: string,
): Promise<JobApplicationRecord> {
  const res = await apiAuthFetch(`/api/v1/me/jobs/${jobId}/apply`, {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ??
        `Could not log application: ${res.status}`,
    );
  }
  notifySavedJobsChanged();
  notifyJobPipelineChanged();
  return res.json();
}
