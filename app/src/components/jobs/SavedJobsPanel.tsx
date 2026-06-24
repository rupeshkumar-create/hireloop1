"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Bookmark } from "lucide-react";
import { fetchSavedJobs } from "@/lib/api/saved-jobs";
import type { MatchedJob } from "@/lib/api/matches";
import { Button, EmptyState } from "@/components/ui";
import { JobCard } from "./JobCard";

type SavedJobsPanelProps = {
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  savedJobIds: Set<string>;
  onSavedChange: (jobId: string, saved: boolean) => void;
  refreshKey?: number;
  className?: string;
};

export function SavedJobsPanel({
  conversationId,
  onRequestIntro,
  savedJobIds,
  onSavedChange,
  refreshKey = 0,
  className,
}: SavedJobsPanelProps) {
  const [jobs, setJobs] = useState<MatchedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setJobs(await fetchSavedJobs());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load saved jobs");
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const visibleJobs = jobs.filter((job) => savedJobIds.has(job.job_id));

  return (
    <div className={className}>
      <div className="flex-1 overflow-y-auto space-y-3 pr-1 pb-6">
        {loading &&
          Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-36 rounded-xl bg-ink-50 animate-pulse border border-ink-100"
            />
          ))}

        {!loading && error && (
          <EmptyState
            icon={<AlertCircle strokeWidth={1.5} />}
            title="Couldn't load saved jobs"
            description={error}
            action={
              <Button variant="secondary" size="sm" onClick={() => void load()}>
                Try again
              </Button>
            }
          />
        )}

        {!loading && !error && visibleJobs.length === 0 && (
          <EmptyState
            icon={<Bookmark strokeWidth={1.5} />}
            title="No saved jobs yet"
            description="Tap the heart on any job card in chat or matches to save it here."
          />
        )}

        {!loading &&
          !error &&
          visibleJobs.map((job) => (
            <JobCard
              key={job.job_id}
              job={job}
              conversationId={conversationId}
              onRequestIntro={onRequestIntro}
              isSaved={savedJobIds.has(job.job_id)}
              onSavedChange={onSavedChange}
              variant="feed"
            />
          ))}
      </div>
    </div>
  );
}
