import type { MatchedJob } from "@/lib/api/matches";

/** Collapse duplicate job cards by stable job_id (keeps first occurrence). */
export function dedupeJobs(jobs: MatchedJob[]): MatchedJob[] {
  const seen = new Set<string>();
  const out: MatchedJob[] = [];
  for (const job of jobs) {
    if (!job.job_id || seen.has(job.job_id)) continue;
    seen.add(job.job_id);
    out.push(job);
  }
  return out;
}
