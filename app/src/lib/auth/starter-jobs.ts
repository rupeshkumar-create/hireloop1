import type { MatchedJob } from "@/lib/api/matches";

const STORAGE_KEY = "hireschema_starter_jobs";

type StarterJobsPayload = {
  jobs: MatchedJob[];
  at: number;
};

/** Persist instant shelf from complete-onboarding for dashboard mount. */
export function storeStarterJobs(jobs: MatchedJob[]): void {
  if (typeof window === "undefined" || jobs.length === 0) return;
  const payload: StarterJobsPayload = { jobs, at: Date.now() };
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

/** Read and clear starter jobs once per session (dashboard first paint). */
export function consumeStarterJobs(): MatchedJob[] | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  sessionStorage.removeItem(STORAGE_KEY);
  try {
    const parsed = JSON.parse(raw) as StarterJobsPayload;
    return Array.isArray(parsed.jobs) && parsed.jobs.length > 0 ? parsed.jobs : null;
  } catch {
    return null;
  }
}
