"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { getApplicationKitForJob } from "@/lib/api/applicationKit";
import type { MatchedJob } from "@/lib/api/matches";
import { saveJob } from "@/lib/api/saved-jobs";
import {
  openLearningRoadmap,
  requestLearningRoadmap,
} from "@/lib/api/learningRoadmap";
import { useToast } from "@/components/ui";
import { useAiOperations } from "@/components/providers/AiOperationsProvider";

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

function kitReadyFromJob(job: MatchedJob, kitByJob: Record<string, AssetStatus>): boolean {
  const local = kitByJob[job.job_id];
  if (local === "ready") return true;
  if (local === "loading" || local === "error") return false;
  return job.action_state === "kit_ready";
}

export function useJobCardAssets(options: UseJobCardAssetsOptions = {}) {
  const router = useRouter();
  const { toast } = useToast();
  const { trackAndWait } = useAiOperations();
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
          setKitByJob((s) => ({ ...s, [job.job_id]: "ready" }));
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
      if (kitReadyFromJob(job, kitByJob)) {
        await openKitPreview(job, "resume");
        return;
      }
      if (status === "loading") return;

      setKitByJob((s) => ({ ...s, [job.job_id]: "loading" }));
      try {
        options.onJobSaved?.(job.job_id);
        // Must finish save BEFORE prepare — inactive/off-market jobs are only
        // eligible for kits when a saved_jobs row exists.
        await saveJob(job.job_id).catch(() => undefined);

        // If a kit already exists (e.g. after refresh / completed in chat), open it
        // instead of bouncing through another prepare deep-link.
        const existing = await getApplicationKitForJob(job.job_id).catch(() => null);
        if (existing?.tailored_resume_id) {
          setResumeIdByJob((s) => ({
            ...s,
            [job.job_id]: existing.tailored_resume_id!,
          }));
          setKitByJob((s) => ({ ...s, [job.job_id]: "ready" }));
          options.onKitReady?.(job);
          await openKitPreview(job, "resume");
          return;
        }

        const params = new URLSearchParams();
        params.set("kit_job_id", job.job_id);
        if (job.title) params.set("kit_title", job.title);
        if (job.company_name) params.set("kit_company", job.company_name);
        router.push(`/dashboard?${params.toString()}`);
      } catch (err) {
        setKitByJob((s) => ({ ...s, [job.job_id]: "error" }));
        toast.error((err as Error).message ?? "Couldn't open Aarya chat");
      }
    },
    [kitByJob, openKitPreview, options, router, toast]
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
        const outcome = await requestLearningRoadmap(job.job_id);
        let roadmapId: string;
        if (outcome.status === "ready") {
          roadmapId = outcome.data.roadmap_id;
        } else {
          const terminal = await trackAndWait(outcome.operation);
          if (terminal.status !== "succeeded" || !terminal.result_id) {
            throw new Error(
              terminal.error_message?.trim() ||
                terminal.message.trim() ||
                "Couldn't build roadmap",
            );
          }
          roadmapId = terminal.result_id;
        }
        setRoadmapIdByJob((s) => ({ ...s, [job.job_id]: roadmapId }));
        await openLearningRoadmap(roadmapId);
        setRoadmapByJob((s) => ({ ...s, [job.job_id]: "ready" }));
      } catch (err) {
        setRoadmapByJob((s) => ({ ...s, [job.job_id]: "error" }));
        toast.error((err as Error).message ?? "Couldn't build roadmap");
      }
    },
    [roadmapByJob, roadmapIdByJob, toast, trackAndWait]
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
