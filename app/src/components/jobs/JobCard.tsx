"use client";

/**
 * JobCard — DESIGN.md compliant card for the match feed.
 *
 * Layout (visual):
 *   ┌──────────────────────────────────────────────────┐
 *   │  [Logo] Company · Location              ● 82%    │
 *   │  Title                                           │
 *   │  Seniority · Employment type · Remote · CTC      │
 *   │  React  TypeScript  Postgres  +3 more            │
 *   │  Aarya's match explanation, 1-2 lines.           │
 *   │  ─────────────────────────────────────────────   │
 *   │  [Request intro]  [Apply]  [Tailor]    [♡]       │
 *   └──────────────────────────────────────────────────┘
 *
 * All visual chrome from <Card>. Buttons from <Button>. Score from <ScoreDot>.
 */

import { useState } from "react";
import { saveJob, unsaveJob } from "@/lib/api/saved-jobs";
import {
  ArrowUpRight,
  Check,
  ExternalLink,
  FileText,
  GraduationCap,
  Heart,
  Loader2,
  Send,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatSalaryRange } from "@/lib/salary";
import type { MatchedJob } from "@/lib/api/matches";
import { Avatar, Badge, Button, Card, ScoreDot, useToast } from "@/components/ui";

interface JobCardProps {
  job: MatchedJob;
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  onDirectApply?: (job: MatchedJob) => void;
  onTailorResume?: (job: MatchedJob) => void;
  tailorStatus?: "idle" | "loading" | "ready" | "error";
  onLearningRoadmap?: (job: MatchedJob) => void;
  roadmapStatus?: "idle" | "loading" | "ready" | "error";
  isSaved?: boolean;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  /** When true, intro / apply are disabled until profile is ready (UI gate only). */
  applyLocked?: boolean;
  onApplyLocked?: () => void;
  /** chat = compact actions for Aarya thread; feed = full matches panel */
  variant?: "feed" | "chat";
  className?: string;
}

// ── Seniority / type labels ──────────────────────────────────────────────────

const SENIORITY_LABELS: Record<string, string> = {
  intern: "Intern",
  junior: "Junior",
  mid: "Mid-level",
  senior: "Senior",
  lead: "Lead",
  director: "Director",
  vp: "VP",
  c_level: "C-Level",
};

const EMP_LABELS: Record<string, string> = {
  full_time: "Full-time",
  contract: "Contract",
  internship: "Internship",
  part_time: "Part-time",
};

// ── Main component ───────────────────────────────────────────────────────────

export function JobCard({
  job,
  onRequestIntro,
  onDirectApply,
  onTailorResume,
  tailorStatus = "idle",
  onLearningRoadmap,
  roadmapStatus = "idle",
  isSaved = false,
  onSavedChange,
  variant = "feed",
  applyLocked = false,
  onApplyLocked,
  className,
}: JobCardProps) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [introSent, setIntroSent] = useState(false);
  const isChat = variant === "chat";

  const tailoring = tailorStatus === "loading";
  const tailoredReady = tailorStatus === "ready";
  const roadmapBuilding = roadmapStatus === "loading";
  const roadmapReady = roadmapStatus === "ready";

  const ctcLabel = formatSalaryRange(job.ctc_min, job.ctc_max, {
    currency: job.salary_currency,
  });

  const locationLabel =
    [job.location_city, job.location_state]
      .filter(Boolean)
      .join(", ") || (job.is_remote ? null : "Onsite");

  const handleIntro = () => {
    if (applyLocked) {
      onApplyLocked?.();
      return;
    }
    setIntroSent(true);
    onRequestIntro?.(job);
  };

  const handleApply = () => {
    if (applyLocked) {
      onApplyLocked?.();
      return;
    }
    onDirectApply?.(job);
    if (job.apply_url) {
      window.open(job.apply_url, "_blank", "noopener,noreferrer");
    }
  };

  const handleRoadmap = () => {
    if (roadmapBuilding || roadmapReady || !onLearningRoadmap) return;
    onLearningRoadmap(job);
  };

  const handleTailor = () => {
    if (tailoring || tailoredReady || !onTailorResume) return;
    onTailorResume(job);
  };

  const handleSaveToggle = async () => {
    if (saving) return;
    setSaving(true);
    const next = !isSaved;
    // Optimistic: flip the heart immediately via parent state, revert on error.
    onSavedChange?.(job.job_id, next);
    try {
      if (next) {
        await saveJob(job.job_id);
        toast.success("Saved to Jobs");
      } else {
        await unsaveJob(job.job_id);
        toast.success("Removed from saved");
      }
    } catch {
      onSavedChange?.(job.job_id, !next);
      toast.error(next ? "Couldn't save job" : "Couldn't remove saved job");
    } finally {
      setSaving(false);
    }
  };

  const tierBandClass =
    job.tier === "strong"
      ? "bg-accent"
      : job.tier === "good"
        ? "bg-amber-400"
        : "bg-ink-200";

  return (
    <Card
      className={cn(
        "relative overflow-hidden hover:shadow-2 transition-shadow duration-fast",
        isChat ? "p-4" : "p-5",
        className
      )}
    >
      <div
        className={cn("absolute left-0 top-0 bottom-0 w-1", tierBandClass)}
        aria-hidden
      />

      {applyLocked && (
        <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-micro text-amber-900">
          Upload a resume or add city + expected CTC to apply or request intros.
        </div>
      )}
      {/* ── Top row: company + title + score ──────────────────────────── */}
      {/* The title/company block is a real link to the full job detail page,
          opened in a new tab so the user keeps their chat / feed context. Using
          an <a target="_blank"> (not an onClick) means cmd/middle-click and
          "open in new tab" all work natively. */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <a
          href={`/jobs/${job.job_id}`}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View full details for ${job.title} (opens in a new tab)`}
          className="flex items-center gap-3 min-w-0 flex-1 text-left rounded-md -m-1 p-1 hover:bg-ink-50 transition-colors duration-fast group"
        >
          <Avatar name={job.company_name ?? "?"} size="md" tone="light" />
          <div className="min-w-0">
            <p className="text-small text-ink-500 truncate">
              {job.company_name ?? "Company"}
              {locationLabel && (
                <>
                  {" "}
                  <span className="text-ink-300">·</span> {locationLabel}
                </>
              )}
            </p>
            <h3 className="text-h3 text-ink-900 leading-tight truncate mt-0.5 group-hover:underline underline-offset-2 decoration-ink-300">
              {job.title}
            </h3>
          </div>
        </a>
        <ScoreDot value={job.overall_score} size={isChat ? "sm" : "md"} label="match" />
      </div>

      {/* ── Tags row ───────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        {job.action_label && (
          <Badge tone="accent">
            <Check className="h-3 w-3 mr-0.5 inline" strokeWidth={2.5} />
            {job.action_label}
          </Badge>
        )}
        {(job.tier || job.tier_label) && (
          <Badge
            tone={
              job.tier === "strong"
                ? "accent"
                : job.tier === "good"
                  ? "strong"
                  : "muted"
            }
          >
            {job.tier === "strong"
              ? "Strong match"
              : job.tier === "good"
                ? "Promising"
                : (job.tier_label ?? "Worth exploring")}
          </Badge>
        )}
        {job.seniority && (
          <Badge>{SENIORITY_LABELS[job.seniority] ?? job.seniority}</Badge>
        )}
        {job.employment_type && (
          <Badge>{EMP_LABELS[job.employment_type] ?? job.employment_type}</Badge>
        )}
        {job.is_remote && <Badge>Remote</Badge>}
        {ctcLabel && <Badge tone="accent">{ctcLabel}</Badge>}
      </div>

      {/* ── Skills chips (matched skills highlighted) + gaps ───────────── */}
      {job.skills_required.length > 0 &&
        (() => {
          const matched = new Set(job.skills_matched ?? []);
          const gaps = job.skills_gap ?? [];
          const hasMatchData = (job.skills_matched?.length ?? 0) > 0 || gaps.length > 0;
          // Show matched skills first so the candidate sees their fit up front.
          const ordered = hasMatchData
            ? [...job.skills_required].sort(
                (a, b) => Number(matched.has(b)) - Number(matched.has(a))
              )
            : job.skills_required;
          return (
            <div className="mb-3 space-y-2">
              {hasMatchData && (
                <p className="text-micro font-medium text-ink-600">
                  ✓ {matched.size} matching skill{matched.size !== 1 ? "s" : ""}
                  {gaps.length > 0 && (
                    <span className="font-normal text-ink-400">
                      {" "}
                      · {gaps.length} to grow into
                    </span>
                  )}
                </p>
              )}
              <div className="flex flex-wrap gap-1">
                {ordered.slice(0, 5).map((skill) => {
                  const isMatch = matched.has(skill);
                  return (
                    <span
                      key={skill}
                      className={cn(
                        "inline-flex items-center gap-1 text-small px-2 py-0.5 rounded-sm",
                        isMatch
                          ? "text-ink-900 bg-ink-100 font-medium"
                          : "text-ink-500 bg-ink-50"
                      )}
                    >
                      {isMatch && <Check className="h-3 w-3" strokeWidth={2.5} />}
                      {skill}
                    </span>
                  );
                })}
                {job.skills_required.length > 5 && (
                  <span className="text-small text-ink-300 px-1 py-0.5">
                    +{job.skills_required.length - 5} more
                  </span>
                )}
              </div>
              {gaps.length > 0 && (
                <p className="text-micro text-ink-500">
                  <span className="font-medium text-ink-600">Worth building: </span>
                  {gaps.slice(0, 4).join(", ")}
                  {gaps.length > 4 ? ` +${gaps.length - 4} more` : ""}
                </p>
              )}
            </div>
          );
        })()}

      {/* ── Explanation ────────────────────────────────────────────────── */}
      {job.explanation && (
        <p className="text-small text-ink-500 leading-relaxed mb-4 line-clamp-2">
          {job.explanation}
        </p>
      )}

      {/* ── Actions ────────────────────────────────────────────────────── */}
      {/* Request intro is the single primary action (the MVP loop). Apply /
          Tailor are secondary. Save is a quiet ghost heart, not a CTA. */}
      <div className="flex items-center gap-2 pt-3 border-t border-ink-100">
        <Button
          variant={introSent ? "secondary" : "primary"}
          size="sm"
          onClick={handleIntro}
          disabled={introSent}
          title={applyLocked ? "Upload a resume or add city + CTC to request intros" : undefined}
          leftIcon={
            introSent ? (
              <Check className="h-3.5 w-3.5" strokeWidth={2} />
            ) : (
              <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
            )
          }
          className="flex-1"
        >
          {introSent ? "Requested" : "Request intro"}
        </Button>

        <Button
          variant="secondary"
          size="sm"
          onClick={handleApply}
          disabled={!applyLocked && !job.apply_url}
          title={applyLocked ? "Upload a resume or add city + CTC to apply" : undefined}
          leftIcon={<ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />}
          className="flex-1"
        >
          Apply
        </Button>

        {!isChat && (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleTailor}
            disabled={tailoring || tailoredReady || !onTailorResume}
            leftIcon={
              tailoring ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
              ) : tailoredReady ? (
                <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={1.5} />
              ) : (
                <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
              )
            }
            className="flex-1"
          >
            {tailoring ? "Tailoring" : tailoredReady ? "Ready" : "Tailor"}
          </Button>
        )}

        {!isChat && onLearningRoadmap && (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRoadmap}
            disabled={roadmapBuilding || roadmapReady}
            leftIcon={
              roadmapBuilding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
              ) : roadmapReady ? (
                <ArrowUpRight className="h-3.5 w-3.5" strokeWidth={1.5} />
              ) : (
                <GraduationCap className="h-3.5 w-3.5" strokeWidth={1.5} />
              )
            }
            className="flex-1"
            title="Generate a personal AI learning roadmap for this role"
          >
            {roadmapBuilding ? "Building" : roadmapReady ? "Open" : "Roadmap"}
          </Button>
        )}

        <Button
          variant="ghost"
          size="sm"
          onClick={() => void handleSaveToggle()}
          disabled={saving}
          aria-label={isSaved ? "Remove from saved" : "Save job"}
          aria-pressed={isSaved}
          title={isSaved ? "Saved" : "Save job"}
          className={cn("shrink-0 px-2", isSaved && "text-accent")}
          leftIcon={
            <Heart
              className="h-3.5 w-3.5"
              strokeWidth={1.5}
              fill={isSaved ? "currentColor" : "none"}
            />
          }
        />
      </div>
    </Card>
  );
}
