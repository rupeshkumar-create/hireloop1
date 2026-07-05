"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Briefcase,
  Bookmark,
  CheckCircle,
  ExternalLink,
  FileText,
  MessageCircle,
  RefreshCw,
} from "@/components/brand/icons";
import {
  fetchJobPipeline,
  type JobPipelineItem,
  type JobPipelineStage,
} from "@/lib/api/job-pipeline";
import { downloadTailoredResume } from "@/lib/api/tailored";
import { Badge, Button, EmptyState } from "@/components/ui";
import { cn } from "@/lib/utils";

const STAGES: { id: JobPipelineStage; label: string }[] = [
  { id: "saved", label: "Saved" },
  { id: "kit_ready", label: "Kit ready" },
  { id: "applied", label: "Applied" },
  { id: "intro_in_progress", label: "Intro" },
  { id: "intro_accepted", label: "Chat open" },
];

const STAGE_TONE: Record<JobPipelineStage, "muted" | "strong" | "accent"> = {
  saved: "muted",
  kit_ready: "accent",
  applied: "strong",
  intro_in_progress: "accent",
  intro_accepted: "strong",
  tracked: "muted",
};

const STAGE_LABEL: Record<JobPipelineStage, string> = {
  saved: "Saved",
  kit_ready: "Kit generated",
  applied: "Applied",
  intro_in_progress: "Intro in progress",
  intro_accepted: "Intro accepted",
  tracked: "Tracked",
};

function stageIndex(stage: JobPipelineStage): number {
  const idx = STAGES.findIndex((s) => s.id === stage);
  return idx >= 0 ? idx : 0;
}

function PipelineSteps({ stage }: { stage: JobPipelineStage }) {
  const current = stageIndex(stage);

  return (
    <div className="flex items-center gap-1 mt-2">
      {STAGES.map((s, i) => (
        <div key={s.id} className="flex items-center gap-1 flex-1 min-w-0">
          <div
            className={cn(
              "h-1.5 flex-1 rounded-sm",
              i <= current ? "bg-accent" : "bg-ink-100",
            )}
            title={s.label}
          />
        </div>
      ))}
    </div>
  );
}

function JobPipelineCard({ item }: { item: JobPipelineItem }) {
  const location = [item.location_city, item.location_state].filter(Boolean).join(", ");
  const canChat = item.stage === "intro_accepted" && item.intro_id;

  return (
    <div className="rounded-lg border border-ink-100 bg-paper-1 p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/jobs/${item.job_id}`}
            className="text-small font-semibold text-ink-900 hover:underline truncate block"
          >
            {item.title}
          </Link>
          <p className="text-micro text-ink-500 truncate">
            {[item.company_name, location || (item.is_remote ? "Remote" : null)]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Badge tone={STAGE_TONE[item.stage]}>{STAGE_LABEL[item.stage]}</Badge>
      </div>

      <PipelineSteps stage={item.stage} />

      <div className="flex flex-wrap gap-2 pt-1">
        {item.saved && (
          <span className="inline-flex items-center gap-1 text-micro text-ink-500">
            <Bookmark className="h-3 w-3" strokeWidth={1.5} />
            Saved
          </span>
        )}
        {item.kit_id && (
          <span className="inline-flex items-center gap-1 text-micro text-ink-500">
            <FileText className="h-3 w-3" strokeWidth={1.5} />
            Resume & cover letter
          </span>
        )}
        {item.application_status && (
          <span className="inline-flex items-center gap-1 text-micro text-ink-500">
            <CheckCircle className="h-3 w-3" strokeWidth={1.5} />
            Applied
          </span>
        )}
        {item.intro_status && (
          <span className="inline-flex items-center gap-1 text-micro text-ink-500 capitalize">
            <MessageCircle className="h-3 w-3" strokeWidth={1.5} />
            Intro {item.intro_status.replace(/_/g, " ")}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2 pt-1">
        {item.kit_id && item.tailored_resume_id && (
          <button
            type="button"
            onClick={() => void downloadTailoredResume(item.tailored_resume_id!)}
            className="text-micro font-medium text-ink-700 hover:text-ink-900 underline"
          >
            Download resume
          </button>
        )}
        {item.mock_interview_id && (
          <Link
            href={`/mock-interview/${item.mock_interview_id}`}
            className="text-micro font-medium text-ink-700 hover:text-ink-900 underline"
          >
            Mock interview
          </Link>
        )}
        {canChat && (
          <Link
            href="/dashboard?panel=inbox"
            className="text-micro font-medium text-accent hover:underline inline-flex items-center gap-1"
          >
            <MessageCircle className="h-3 w-3" strokeWidth={1.5} />
            Open recruiter chat
          </Link>
        )}
        {item.apply_url && (
          <a
            href={item.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-micro font-medium text-ink-700 hover:text-ink-900 inline-flex items-center gap-1"
          >
            Apply link
            <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
          </a>
        )}
      </div>
    </div>
  );
}

export function JobTrackerPanel({ className }: { className?: string }) {
  const [items, setItems] = useState<JobPipelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await fetchJobPipeline());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className={cn("h-full overflow-y-auto p-5 space-y-4", className)}>
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-small font-semibold text-ink-900">Job tracker</p>
          <p className="text-micro text-ink-500">
            Saved roles, application kits, applies, and intro status in one place.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void load()}
          loading={loading}
          leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
        >
          Refresh
        </Button>
      </div>

      {error && (
        <p className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
          {error}
        </p>
      )}

      {loading && items.length === 0 && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-28 rounded-lg bg-ink-100 animate-skeleton" />
          ))}
        </div>
      )}

      {!loading && items.length === 0 && (
        <EmptyState
          icon={<Briefcase strokeWidth={1.5} />}
          title="No tracked jobs yet"
          description="Save a role or ask Aarya to prepare an application kit — your pipeline will show up here."
        />
      )}

      {items.length > 0 && (
        <div className="space-y-3">
          {items.map((item) => (
            <JobPipelineCard key={item.job_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
