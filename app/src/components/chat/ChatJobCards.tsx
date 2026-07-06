"use client";

import type { MatchedJob } from "@/lib/api/matches";
import { dedupeJobs } from "@/lib/chat/dedupeJobs";
import {
  applyJobCardFilters,
  jobFiltersLabel,
  type JobCardFilters,
} from "@/lib/chat/jobFilters";
import { JobCard } from "@/components/jobs/JobCard";

type ChatJobCardsProps = {
  jobs: MatchedJob[];
  filters?: JobCardFilters;
  conversationId?: string;
  savedJobIds: Set<string>;
  onSavedChange: (jobId: string, saved: boolean) => void;
  onRequestIntro?: (job: MatchedJob) => void;
  onApply?: (job: MatchedJob) => void;
  onWhyFit?: (job: MatchedJob) => void;
};

export function ChatJobCards({
  jobs,
  filters = {},
  conversationId,
  savedJobIds,
  onSavedChange,
  onRequestIntro,
  onApply,
  onWhyFit,
}: ChatJobCardsProps) {
  const filtered = applyJobCardFilters(dedupeJobs(jobs), filters);
  if (!filtered.length) {
    const hint = jobFiltersLabel(filters);
    return (
      <p className="text-small text-ink-500">
        {hint
          ? `No roles match your filter (${hint}). Try widening criteria or ask Aarya to search again.`
          : "No roles to show."}
      </p>
    );
  }

  const filterHint = jobFiltersLabel(filters);

  return (
    <div className="w-full space-y-3">
      <p className="text-small font-medium text-ink-600">
        {filtered.length} role{filtered.length !== 1 ? "s" : ""} found
        {filterHint ? ` · ${filterHint}` : ""}
      </p>
      <div className="space-y-3">
        {filtered.map((job) => (
          <JobCard
            key={job.job_id}
            job={job}
            conversationId={conversationId}
            onRequestIntro={onRequestIntro}
            onDirectApply={
              onApply ??
              ((j) => {
                if (j.apply_url) {
                  window.open(j.apply_url, "_blank", "noopener,noreferrer");
                }
              })
            }
            onWhyFit={onWhyFit}
            isSaved={savedJobIds.has(job.job_id)}
            onSavedChange={onSavedChange}
            variant="chat"
          />
        ))}
      </div>
    </div>
  );
}
