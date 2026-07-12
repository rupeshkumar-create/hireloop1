"use client";

/**
 * JobCard — minimal match row.
 * Title, company, one fit score, salary/location, one primary CTA.
 * Detail (skills, scores, explanation) lives behind “Why this match”.
 */

import { useEffect, useRef, useState } from "react";
import { saveJob, unsaveJob } from "@/lib/api/saved-jobs";
import {
  Check,
  ChevronDown,
  ExternalLink,
  FileText,
  GraduationCap,
  Heart,
  Loader2,
  MoreHorizontal,
  Send,
} from "@/components/brand/icons";
import { BTN_CHIP_ACTIVE } from "@/lib/button-classes";
import { cn } from "@/lib/utils";
import { formatSalaryRange } from "@/lib/salary";
import type { MatchedJob } from "@/lib/api/matches";
import { Avatar, Button, Card, ScoreDot, useToast } from "@/components/ui";

interface JobCardProps {
  job: MatchedJob;
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  onDirectApply?: (job: MatchedJob) => void;
  onTailorResume?: (job: MatchedJob) => void;
  onWhyFit?: (job: MatchedJob) => void;
  tailorStatus?: "idle" | "loading" | "ready" | "error";
  onOpenKitPreview?: (job: MatchedJob, tab: "resume" | "cover_letter" | "interview_prep") => void;
  onLearningRoadmap?: (job: MatchedJob) => void;
  roadmapStatus?: "idle" | "loading" | "ready" | "error";
  isSaved?: boolean;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  /** When true, intro / apply are disabled until profile is ready (UI gate only). */
  applyLocked?: boolean;
  onApplyLocked?: () => void;
  /** chat = compact actions for Aarya thread; feed = full matches panel */
  variant?: "feed" | "chat";
  /** When set, show this date label instead of posted-ago (job history mode). */
  historyDateLabel?: string | null;
  className?: string;
}

export function JobCard({
  job,
  onRequestIntro,
  onDirectApply,
  onTailorResume,
  onWhyFit,
  tailorStatus = "idle",
  onOpenKitPreview,
  onLearningRoadmap,
  roadmapStatus = "idle",
  isSaved = false,
  onSavedChange,
  variant = "feed",
  applyLocked = false,
  onApplyLocked,
  historyDateLabel,
  className,
}: JobCardProps) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [whyOpen, setWhyOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [introSent, setIntroSent] = useState(
    () => job.action_state === "intro" || Boolean(job.action_label?.toLowerCase().includes("intro")),
  );
  const [applied, setApplied] = useState(
    () =>
      job.action_state === "applied" ||
      Boolean(job.action_label?.toLowerCase().includes("applied")),
  );
  const isChat = variant === "chat";

  const tailoring = tailorStatus === "loading";
  const tailoredReady =
    tailorStatus === "ready" ||
    (tailorStatus === "idle" && job.action_state === "kit_ready");
  const roadmapBuilding = roadmapStatus === "loading";
  const roadmapReady = roadmapStatus === "ready";

  const ctcLabel = formatSalaryRange(job.ctc_min, job.ctc_max, {
    currency: job.salary_currency,
  });

  const locationLabel =
    [job.location_city, job.location_state]
      .filter(Boolean)
      .join(", ") || (job.is_remote ? "Remote" : null);

  const metaLine = [ctcLabel, locationLabel].filter(Boolean).join(" · ");

  const statusLabel =
    historyDateLabel ??
    job.action_label ??
    (job.fit_recommendation === "stretch"
      ? "Stretch"
      : job.fit_recommendation === "skip"
        ? "Skip"
        : null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  const handleIntro = () => {
    if (applyLocked) {
      onApplyLocked?.();
      return;
    }
    if (introSent) return;
    setIntroSent(true);
    onSavedChange?.(job.job_id, true);
    onRequestIntro?.(job);
  };

  const handleApply = () => {
    if (applyLocked) {
      onApplyLocked?.();
      return;
    }
    if (applied) {
      if (job.apply_url) {
        window.open(job.apply_url, "_blank", "noopener,noreferrer");
      }
      return;
    }
    setApplied(true);
    onSavedChange?.(job.job_id, true);
    onDirectApply?.(job);
    if (job.apply_url) {
      window.open(job.apply_url, "_blank", "noopener,noreferrer");
    }
  };

  const handleRoadmap = () => {
    setMenuOpen(false);
    if (roadmapReady) {
      onLearningRoadmap?.(job);
      return;
    }
    if (roadmapBuilding || !onLearningRoadmap) return;
    onLearningRoadmap(job);
  };

  const handleTailor = () => {
    setMenuOpen(false);
    if (tailoredReady) {
      onOpenKitPreview?.(job, "resume");
      return;
    }
    if (tailoring || !onTailorResume) return;
    onTailorResume(job);
  };

  const handleSaveToggle = async () => {
    if (saving) return;
    setSaving(true);
    setMenuOpen(false);
    const next = !isSaved;
    onSavedChange?.(job.job_id, next);
    try {
      if (next) {
        await saveJob(job.job_id);
        toast.success("Saved — open Saved tab to build your application");
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

  const hasWhyDetail = Boolean(
    job.explanation ||
      job.triage_notes ||
      job.skills_required.length > 0 ||
      job.skills_score != null ||
      job.experience_score != null ||
      job.career_alignment_score != null ||
      job.salary_benchmark?.vs_market_label,
  );

  const primaryLabel = introSent
    ? "Intro requested"
    : applied
      ? "Applied"
      : "Request intro";

  return (
    <Card
      className={cn(
        "relative overflow-hidden hover:shadow-2 transition-shadow duration-fast",
        isChat ? "p-4" : "p-5",
        className,
      )}
    >
      {applyLocked && (
        <p className="mb-3 text-micro text-amber-900">
          Add a resume or city + expected CTC to apply or request intros.
        </p>
      )}

      <div className="flex items-start justify-between gap-3">
        <a
          href={`/jobs/${job.job_id}`}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`View full details for ${job.title} (opens in a new tab)`}
          className="flex items-center gap-3 min-w-0 flex-1 text-left rounded-md -m-1 p-1 hover:bg-ink-50 transition-colors duration-fast group"
        >
          <Avatar
            name={job.company_name ?? "?"}
            src={job.company_logo_url}
            size="md"
            tone="light"
            className="rounded-md"
          />
          <div className="min-w-0">
            <p className="text-small text-ink-500 truncate">{job.company_name ?? "Company"}</p>
            <h3 className="text-h3 text-ink-900 leading-tight truncate mt-0.5 group-hover:underline underline-offset-2 decoration-ink-300">
              {job.title}
            </h3>
          </div>
        </a>
        <ScoreDot value={job.overall_score} size={isChat ? "sm" : "md"} label="match" />
      </div>

      {(metaLine || statusLabel) && (
        <p className="mt-2 text-small text-ink-500 truncate">
          {metaLine}
          {metaLine && statusLabel ? " · " : null}
          {statusLabel}
        </p>
      )}

      {hasWhyDetail && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => {
              if (isChat && onWhyFit && !whyOpen) onWhyFit(job);
              setWhyOpen((v) => !v);
            }}
            className="inline-flex items-center gap-1 text-small text-ink-600 hover:text-ink-900 transition-colors"
            aria-expanded={whyOpen}
          >
            Why this match
            <ChevronDown
              className={cn("h-3.5 w-3.5 transition-transform", whyOpen && "rotate-180")}
              strokeWidth={1.5}
            />
          </button>

          {whyOpen && (
            <div className="mt-2 space-y-2 border-t border-ink-100 pt-2 animate-fade-in">
              {(job.skills_score != null ||
                job.experience_score != null ||
                job.career_alignment_score != null) && (
                <p className="text-micro text-ink-500">
                  {job.skills_score != null && (
                    <span>Skills {Math.round(job.skills_score * 100)}</span>
                  )}
                  {job.experience_score != null && (
                    <span>
                      {job.skills_score != null ? " · " : ""}
                      Experience {Math.round(job.experience_score * 100)}
                    </span>
                  )}
                  {job.career_alignment_score != null && (
                    <span>
                      {" · "}Career {Math.round(job.career_alignment_score * 100)}
                    </span>
                  )}
                  {job.culture_score != null && (
                    <span>
                      {" · "}Culture {Math.round(job.culture_score * 100)}
                    </span>
                  )}
                </p>
              )}

              {job.triage_notes && (
                <p className="text-micro text-ink-600 line-clamp-3">{job.triage_notes}</p>
              )}

              {job.salary_benchmark?.vs_market_label && (
                <p className="text-micro text-ink-500">{job.salary_benchmark.vs_market_label}</p>
              )}

              {job.skills_required.length > 0 &&
                (() => {
                  const matched = new Set(job.skills_matched ?? []);
                  const gaps = job.skills_gap ?? [];
                  const hasMatchData =
                    (job.skills_matched?.length ?? 0) > 0 || gaps.length > 0;
                  const ordered = hasMatchData
                    ? [...job.skills_required].sort(
                        (a, b) => Number(matched.has(b)) - Number(matched.has(a)),
                      )
                    : job.skills_required;
                  return (
                    <div className="space-y-1.5">
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
                                  : "text-ink-500 bg-ink-50",
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
                          Worth building: {gaps.slice(0, 4).join(", ")}
                          {gaps.length > 4 ? ` +${gaps.length - 4} more` : ""}
                        </p>
                      )}
                    </div>
                  );
                })()}

              {job.explanation && (
                <p className="text-small text-ink-500 leading-relaxed line-clamp-3">
                  {job.explanation}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="mt-4 flex items-center gap-2 pt-3 border-t border-ink-100">
        <Button
          variant={introSent || applied ? "secondary" : "primary"}
          size="sm"
          onClick={handleIntro}
          disabled={introSent}
          className="shrink-0"
          leftIcon={
            introSent || applied ? (
              <Check className="h-3.5 w-3.5" strokeWidth={2} />
            ) : (
              <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
            )
          }
        >
          {primaryLabel}
        </Button>

        <div className="relative ml-auto" ref={menuRef}>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="More actions"
            aria-expanded={menuOpen}
            className="shrink-0 px-2"
            leftIcon={<MoreHorizontal className="h-4 w-4" strokeWidth={1.5} />}
          />
          {menuOpen && (
            <div className="absolute right-0 bottom-full mb-1 z-20 min-w-[11rem] rounded-lg border border-ink-100 bg-paper-1 py-1 shadow-2 animate-fade-in">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  handleApply();
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-small text-ink-800 hover:bg-ink-50"
              >
                <ExternalLink className="h-3.5 w-3.5 text-ink-400" strokeWidth={1.5} />
                {applied ? "Open apply link" : "Apply"}
              </button>
              {!isChat && (
                <button
                  type="button"
                  onClick={handleTailor}
                  disabled={tailoring || (!onTailorResume && !tailoredReady)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-small text-ink-800 hover:bg-ink-50 disabled:opacity-50"
                >
                  {tailoring ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-ink-400" strokeWidth={1.5} />
                  ) : (
                    <FileText className="h-3.5 w-3.5 text-ink-400" strokeWidth={1.5} />
                  )}
                  {tailoredReady ? "Preview kit" : "Application kit"}
                </button>
              )}
              {!isChat && onLearningRoadmap && (
                <button
                  type="button"
                  onClick={handleRoadmap}
                  disabled={roadmapBuilding}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-small text-ink-800 hover:bg-ink-50 disabled:opacity-50"
                >
                  {roadmapBuilding ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-ink-400" strokeWidth={1.5} />
                  ) : (
                    <GraduationCap className="h-3.5 w-3.5 text-ink-400" strokeWidth={1.5} />
                  )}
                  {roadmapReady ? "Open roadmap" : "Learning roadmap"}
                </button>
              )}
              <button
                type="button"
                onClick={() => void handleSaveToggle()}
                disabled={saving}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-2 text-left text-small hover:bg-ink-50",
                  isSaved ? "text-ink-900" : "text-ink-800",
                )}
              >
                <Heart
                  className={cn("h-3.5 w-3.5", isSaved ? BTN_CHIP_ACTIVE : "text-ink-400")}
                  strokeWidth={1.5}
                  fill={isSaved ? "currentColor" : "none"}
                />
                {isSaved ? "Unsave" : "Save"}
              </button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
