"use client";

import { useCallback, useState } from "react";
import { getApplicationKitForJob, prepareApplicationKit } from "@/lib/api/applicationKit";
import type { MatchedJob } from "@/lib/api/matches";
import { saveJob } from "@/lib/api/saved-jobs";
import {
  openLearningRoadmap,
  pollLearningRoadmap,
  requestLearningRoadmap,
} from "@/lib/api/learningRoadmap";
import { useToast } from "@/components/ui";

export type AssetStatus = "idle" | "loading" | "ready" | "error";

export type KitPreviewTab = "resume" | "cover_letter" | "interview_prep";

export type KitPreviewState = {
  jobId: string;
  jobTitle: string;
  resumeId: string | null;
  tab: KitPreviewTab;
} | null;

export type UseJobCardAssetsOptions = {
  onKitReady?: (job: MatchedJob) => void;
  onJobSaved?: (jobId: string) => void;
};

export function useJobCardAssets(options: UseJobCardAssetsOptions = {}) {
  const { toast } = useToast();
  const [kitByJob, setKitByJob] = useState<Record<string, AssetStatus>>({});
  const [roadmapByJob, setRoadmapByJob] = useState<Record<string, AssetStatus>>({});
  const [resumeIdByJob, setResumeIdByJob] = useState<Record<string, string>>({});
  const [roadmapIdByJob, setRoadmapIdByJob] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<KitPreviewState>(null);

  const openKitPreview = useCallback(
    async (job: MatchedJob, tab: KitPreviewTab = "resume") => {
      let resumeId: string | null = resumeIdByJob[job.job_id] ?? null;
      if (!resumeId) {
        const kit = await getApplicationKitForJob(job.job_id).catch(() => null);
        resumeId = kit?.tailored_resume_id ?? null;
        if (resumeId) {
          setResumeIdByJob((s) => ({ ...s, [job.job_id]: resumeId! }));
        }
      }
      setPreview({
        jobId: job.job_id,
        jobTitle: job.title,
        resumeId,
        tab,
      });
    },
    [resumeIdByJob]
  );

  const closePreview = useCallback(() => setPreview(null), []);

  const handlePrepareKit = useCallback(
    async (job: MatchedJob) => {
      const status = kitByJob[job.job_id];
      if (status === "ready") {
        await openKitPreview(job, "resume");
        return;
      }
      if (status === "loading") return;

      setKitByJob((s) => ({ ...s, [job.job_id]: "loading" }));
      try {
        options.onJobSaved?.(job.job_id);
        void saveJob(job.job_id).catch(() => undefined);
        const kit = await prepareApplicationKit(job.job_id);
        const resumeId = kit.resume?.resume_id ?? null;
        if (resumeId) {
          setResumeIdByJob((s) => ({ ...s, [job.job_id]: resumeId }));
        }
        setKitByJob((s) => ({ ...s, [job.job_id]: "ready" }));
        setPreview({
          jobId: job.job_id,
          jobTitle: job.title,
          resumeId,
          tab: resumeId ? "resume" : kit.cover_letter ? "cover_letter" : "interview_prep",
        });
        options.onKitReady?.(job);
      } catch (err) {
        setKitByJob((s) => ({ ...s, [job.job_id]: "error" }));
        toast.error((err as Error).message ?? "Couldn't prepare application kit");
      }
    },
    [kitByJob, openKitPreview, options, toast]
  );

  const handleLearningRoadmap = useCallback(
    async (job: MatchedJob) => {
      const status = roadmapByJob[job.job_id];
      if (status === "ready") {
        const roadmapId = roadmapIdByJob[job.job_id];
        if (roadmapId) {
          try {
            await openLearningRoadmap(roadmapId);
          } catch (err) {
            toast.error((err as Error).message ?? "Couldn't open roadmap");
          }
        }
        return;
      }
      if (status === "loading") return;

      setRoadmapByJob((s) => ({ ...s, [job.job_id]: "loading" }));
      try {
        const started = await requestLearningRoadmap(job.job_id);
        if (started.status === "ready" && started.download_path) {
          const id = started.download_path.split("/").pop();
          if (id) {
            setRoadmapIdByJob((s) => ({ ...s, [job.job_id]: id }));
            await openLearningRoadmap(id);
          }
          setRoadmapByJob((s) => ({ ...s, [job.job_id]: "ready" }));
          return;
        }
        const roadmapId = started.roadmap_id;
        if (!roadmapId) {
          throw new Error(started.message ?? "No roadmap id returned");
        }
        const ready = await pollLearningRoadmap(roadmapId);
        setRoadmapIdByJob((s) => ({ ...s, [job.job_id]: ready.id }));
        await openLearningRoadmap(ready.id);
        setRoadmapByJob((s) => ({ ...s, [job.job_id]: "ready" }));
      } catch (err) {
        setRoadmapByJob((s) => ({ ...s, [job.job_id]: "error" }));
        toast.error((err as Error).message ?? "Couldn't build roadmap");
      }
    },
    [roadmapByJob, roadmapIdByJob, toast]
  );

  return {
    kitByJob,
    roadmapByJob,
    preview,
    openKitPreview,
    closePreview,
    handlePrepareKit,
    handleLearningRoadmap,
  };
}
