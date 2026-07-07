"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Bookmark, ChevronRight } from "@/components/brand/icons";
import { fetchSavedJobs } from "@/lib/api/saved-jobs";
import type { MatchedJob } from "@/lib/api/matches";
import { useJobCardAssets } from "@/hooks/useJobCardAssets";
import { ResumePreviewModal } from "@/components/resumes/ResumePreviewModal";
import { Button, EmptyState } from "@/components/ui";
import { JobCard } from "./JobCard";
import { cn } from "@/lib/utils";

type SavedJobsPanelProps = {
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  savedJobIds: Set<string>;
  onSavedChange: (jobId: string, saved: boolean) => void;
  refreshKey?: number;
  onKitsReadyCountChange?: (count: number) => void;
  className?: string;
};

export function SavedJobsPanel({
  conversationId,
  onRequestIntro,
  savedJobIds,
  onSavedChange,
  refreshKey = 0,
  onKitsReadyCountChange,
  className,
}: SavedJobsPanelProps) {
  const [jobs, setJobs] = useState<MatchedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [queueIndex, setQueueIndex] = useState(0);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const {
    kitByJob,
    roadmapByJob,
    preview,
    openKitPreview,
    closePreview,
    handlePrepareKit,
    handleLearningRoadmap,
  } = useJobCardAssets({
    onJobSaved: (jobId) => onSavedChange(jobId, true),
  });

  const kitsReadyCount = Object.values(kitByJob).filter((s) => s === "ready").length;

  useEffect(() => {
    onKitsReadyCountChange?.(kitsReadyCount);
  }, [kitsReadyCount, onKitsReadyCountChange]);

  const scrollToJob = useCallback((index: number) => {
    const job = jobs[index];
    if (!job) return;
    cardRefs.current[job.job_id]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [jobs]);

  const goToNextJob = useCallback(
    (preferWithoutKit = false) => {
      if (jobs.length === 0) return;
      let next = queueIndex;
      if (preferWithoutKit) {
        const start = queueIndex + 1;
        const idx = jobs.findIndex(
          (j, i) => i >= start && kitByJob[j.job_id] !== "ready",
        );
        if (idx >= 0) {
          next = idx;
        } else {
          const wrap = jobs.findIndex((j) => kitByJob[j.job_id] !== "ready");
          next = wrap >= 0 ? wrap : Math.min(queueIndex + 1, jobs.length - 1);
        }
      } else {
        next = Math.min(queueIndex + 1, jobs.length - 1);
      }
      setQueueIndex(next);
      scrollToJob(next);
    },
    [jobs, queueIndex, kitByJob, scrollToJob],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await fetchSavedJobs();
      setJobs(list);
      setQueueIndex((i) => Math.min(i, Math.max(0, list.length - 1)));
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

  const handleClosePreview = useCallback(() => {
    closePreview();
    window.setTimeout(() => goToNextJob(true), 300);
  }, [closePreview, goToNextJob]);

  return (
    <div className={cn("flex flex-col h-full min-h-0", className)}>
      {!loading && !error && jobs.length > 0 && (
        <div className="shrink-0 flex items-center justify-between gap-3 px-5 py-3 border-b border-ink-100 bg-paper-0">
          <div>
            <p className="text-small font-medium text-ink-900">
              Saved queue · Job {queueIndex + 1} of {jobs.length}
            </p>
            <p className="text-micro text-ink-500">
              Generate an application, review it, then move to the next role.
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={queueIndex >= jobs.length - 1 && kitsReadyCount >= jobs.length}
            onClick={() => goToNextJob(false)}
            rightIcon={<ChevronRight className="h-4 w-4" strokeWidth={1.5} />}
          >
            Next job
          </Button>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto space-y-3 px-5 py-4 pr-1">
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

        {!loading && !error && jobs.length === 0 && (
          <EmptyState
            icon={<Bookmark strokeWidth={1.5} />}
            title="No saved jobs yet"
            description="Tap the heart on any match to save it here — then generate applications one by one."
          />
        )}

        {!loading &&
          !error &&
          jobs.map((job, index) => {
            const isFocused = index === queueIndex;
            const kitStatus = kitByJob[job.job_id] ?? "idle";
            return (
              <div
                key={job.job_id}
                ref={(el) => {
                  cardRefs.current[job.job_id] = el;
                }}
                className={cn(
                  "rounded-xl transition-shadow",
                  isFocused && "ring-2 ring-accent/40 ring-offset-2 ring-offset-paper-0",
                )}
              >
                {isFocused && kitStatus !== "ready" && (
                  <p className="text-micro font-medium text-accent mb-2 px-1">
                    ↑ Your turn — tap Generate application
                  </p>
                )}
                <JobCard
                  job={job}
                  conversationId={conversationId}
                  onRequestIntro={onRequestIntro}
                  onTailorResume={handlePrepareKit}
                  tailorStatus={kitStatus}
                  onOpenKitPreview={openKitPreview}
                  onLearningRoadmap={handleLearningRoadmap}
                  roadmapStatus={roadmapByJob[job.job_id] ?? "idle"}
                  isSaved={savedJobIds.has(job.job_id)}
                  onSavedChange={onSavedChange}
                  variant="feed"
                />
              </div>
            );
          })}
      </div>

      <ResumePreviewModal
        open={!!preview}
        onClose={handleClosePreview}
        resumeId={preview?.resumeId ?? null}
        jobId={preview?.jobId ?? null}
        jobTitle={preview?.jobTitle}
        initialTab={preview?.tab}
      />
    </div>
  );
}
