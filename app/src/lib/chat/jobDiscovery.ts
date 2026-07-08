/**
 * Helpers for the post–job-search discovery poll (Apify ingest + re-score).
 */

export const JOB_DISCOVERY_POLL_MS = 3_000;
export const JOB_DISCOVERY_TIMEOUT_MS = 4 * 60_000;

export const JOB_DISCOVERY_FALLBACK_LABELS = [
  "Searching live roles in your market",
  "Pulling openings from LinkedIn",
  "Saving new roles to your index",
  "Scoring matches for your profile",
  "Ranking your best fits",
] as const;

export function shouldWatchForJobDiscovery(jobCount: number, userWasJobSearch: boolean): boolean {
  return userWasJobSearch && jobCount === 0;
}

export function ingestProgressLabel(progress: Record<string, unknown> | undefined): string | null {
  if (!progress) return null;
  const phase = String(progress.phase ?? "");
  const query = typeof progress.query === "string" ? progress.query.trim() : "";
  const step = Number(progress.step);
  const total = Number(progress.total);
  const stepLabel =
    Number.isFinite(step) && Number.isFinite(total) && total > 0
      ? ` (${step}/${total})`
      : "";

  switch (phase) {
    case "queued":
      return "Queuing live job search on LinkedIn…";
    case "searching":
      return query
        ? `Finding live openings for ${query}${stepLabel}…`
        : `Finding live openings${stepLabel}…`;
    case "stored":
      return query
        ? `Saving roles for ${query}${stepLabel}…`
        : `Saving new roles${stepLabel}…`;
    case "scoring":
      return "Scoring matches for your profile…";
    case "scored": {
      const scored = Number(progress.scored);
      if (Number.isFinite(scored) && scored > 0) {
        return `Ranked ${scored} roles for your profile…`;
      }
      return "Finishing match scores…";
    }
    case "completed":
      return "Wrapping up — loading your matches…";
    default:
      return null;
  }
}
