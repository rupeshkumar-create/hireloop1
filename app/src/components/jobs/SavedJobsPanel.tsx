"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Bookmark } from "lucide-react";
import { fetchSavedJobs } from "@/lib/api/saved-jobs";
import type { MatchedJob } from "@/lib/api/matches";
import {
  openTailoredDownload,
  pollTailoredResume,
  requestTailoredResume,
} from "@/lib/api/tailored";
import {
  openLearningRoadmap,
  pollLearningRoadmap,
  requestLearningRoadmap,
} from "@/lib/api/learningRoadmap";
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

  // Per-job tailored-resume state (mirrors MatchFeed).
  const [tailorByJob, setTailorByJob] = useState<
    Record<string, "idle" | "loading" | "ready" | "error">
  >({});

  const handleTailorResume = useCallback(async (job: MatchedJob) => {
    setTailorByJob((s) => ({ ...s, [job.job_id]: "loading" }));
    try {
      const started = await requestTailoredResume(job.job_id);
      if (started.status === "ready" && started.download_path) {
        const id = started.download_path.split("/").pop();
        if (id) openTailoredDownload(id);
        setTailorByJob((s) => ({ ...s, [job.job_id]: "ready" }));
        return;
      }
      const resumeId = started.resume_id;
      if (!resumeId) {
        throw new Error(started.message ?? "No resume id returned");
      }
      const ready = await pollTailoredResume(resumeId);
      openTailoredDownload(ready.id);
      setTailorByJob((s) => ({ ...s, [job.job_id]: "ready" }));
    } catch {
      setTailorByJob((s) => ({ ...s, [job.job_id]: "error" }));
    }
  }, []);

  // Per-job learning-roadmap state.
  const [roadmapByJob, setRoadmapByJob] = useState<
    Record<string, "idle" | "loading" | "ready" | "error">
  >({});

  const handleLearningRoadmap = useCallback(async (job: MatchedJob) => {
    setRoadmapByJob((s) => ({ ...s, [job.job_id]: "loading" }));
    try {
      const started = await requestLearningRoadmap(job.job_id);
      if (started.status === "ready" && started.download_path) {
        const id = started.download_path.split("/").pop();
        if (id) await openLearningRoadmap(id);
        setRoadmapByJob((s) => ({ ...s, [job.job_id]: "ready" }));
        return;
      }
      const roadmapId = started.roadmap_id;
      if (!roadmapId) {
        throw new Error(started.message ?? "No roadmap id returned");
      }
      const ready = await pollLearningRoadmap(roadmapId);
      await openLearningRoadmap(ready.id);
      setRoadmapByJob((s) => ({ ...s, [job.job_id]: "ready" }));
    } catch {
      setRoadmapByJob((s) => ({ ...s, [job.job_id]: "error" }));
    }
  }, []);

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
              onTailorResume={handleTailorResume}
              tailorStatus={tailorByJob[job.job_id] ?? "idle"}
              onLearningRoadmap={handleLearningRoadmap}
              roadmapStatus={roadmapByJob[job.job_id] ?? "idle"}
              isSaved={savedJobIds.has(job.job_id)}
              onSavedChange={onSavedChange}
              variant="feed"
            />
          ))}
      </div>
    </div>
  );
}
