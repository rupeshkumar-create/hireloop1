"use client";

/**
 * CareerPathPanel — the "Find jobs" experience.
 *
 * Flow (matches the user's intent — career path FIRST, then jobs):
 *   1. Generate a career path from the candidate's profile (build_career_path).
 *      → current role, a few next steps, and concrete target job titles.
 *   2. "Find jobs for this path" surfaces real openings for those target roles
 *      (existing DB matches immediately) and fires a background Apify top-up +
 *      re-score, shown by the "Aarya is scanning fresh roles…" indicator.
 *
 * Visual structure:
 *   ┌─ summary ─────────────────────────────────┐
 *   │  current → next → future  (timeline)       │
 *   │  target-role chips                         │
 *   │  [Find jobs for this path]   [Regenerate]  │
 *   ├─ jobs ────────────────────────────────────┤
 *   │  scanning indicator (while refreshing)     │
 *   │  <JobCard> list                            │
 *   └────────────────────────────────────────────┘
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Loader2,
  RefreshCw,
  Route,
  Search,
} from "@/components/brand/icons";
import { cn } from "@/lib/utils";
import {
  fetchCareerPath,
  findJobsForPath,
  generateCareerPath,
  prioritizeCareerPath,
  type CareerPath,
  type CareerStep,
} from "@/lib/api/career";
import type { MatchedJob } from "@/lib/api/matches";
import { useJobCardAssets } from "@/hooks/useJobCardAssets";
import { ResumePreviewModal } from "@/components/resumes/ResumePreviewModal";
import { Badge, Button, Card, CardBody, EmptyState } from "@/components/ui";
import { useAiOperations } from "@/components/providers/AiOperationsProvider";
import { AiOperationProgress } from "@/components/operations/AiOperationProgress";
import {
  resolveReadyOrAccepted,
  terminalOperationError,
  waitForTrackedOperation,
} from "@/lib/operations/resolve";
import {
  AI_OPERATION_KINDS,
  findActiveOperationByKind,
} from "@/lib/operations/kinds";
import { JobCard } from "./JobCard";

interface CareerPathPanelProps {
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  onDirectApply?: (job: MatchedJob) => void;
  savedJobIds?: Set<string>;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  className?: string;
}

// ── Step level styling ─────────────────────────────────────────────────────────

const LEVEL_META: Record<
  string,
  { label: string; dot: string; ring: string }
> = {
  current: { label: "You are here", dot: "bg-accent", ring: "ring-accent/30" },
  next: { label: "Next step", dot: "bg-ink-900", ring: "ring-ink-900/15" },
  future: { label: "Future", dot: "bg-ink-300", ring: "ring-ink-200" },
};

export function CareerPathPanel({
  conversationId,
  onRequestIntro,
  onDirectApply,
  savedJobIds = new Set(),
  onSavedChange,
  className,
}: CareerPathPanelProps) {
  const [path, setPath] = useState<CareerPath | null>(null);
  const [loadingPath, setLoadingPath] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [autoBuilding, setAutoBuilding] = useState(false);
  const [pathError, setPathError] = useState<string | null>(null);
  const [preferredTitle, setPreferredTitle] = useState<string>("");
  const [customTitle, setCustomTitle] = useState("");
  const [savingPreferred, setSavingPreferred] = useState(false);

  const [jobs, setJobs] = useState<MatchedJob[]>([]);
  const [findingJobs, setFindingJobs] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [sourceAvailable, setSourceAvailable] = useState(true);
  const [activeOpId, setActiveOpId] = useState<string | null>(null);
  const {
    trackAndWait,
    waitForOperation,
    operations,
    restoreState,
    cancelOperation,
    retryOperation,
  } = useAiOperations();

  const {
    kitByJob,
    roadmapByJob,
    preview,
    openKitPreview,
    closePreview,
    handlePrepareKit,
    handleLearningRoadmap,
  } = useJobCardAssets();

  // ── Load the latest path on mount ────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    fetchCareerPath()
      .then((p) => {
        if (cancelled) return;
        setPath(p);
        const pick = p?.prioritized_title ?? p?.target_titles?.[0] ?? "";
        setPreferredTitle(pick);
      })
      .catch((err) => {
        if (!cancelled) setPathError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoadingPath(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Restore / terminal handling for career_path_generate only (never "pending").
  useEffect(() => {
    if (path) return;

    const active = findActiveOperationByKind(
      operations,
      AI_OPERATION_KINDS.careerPathGenerate,
    );
    if (active) {
      setActiveOpId(active.id);
      setAutoBuilding(true);
      setPathError(null);
      return;
    }

    if (!activeOpId) return;
    const tracked = operations[activeOpId];
    if (!tracked || tracked.kind !== AI_OPERATION_KINDS.careerPathGenerate) {
      return;
    }

    if (tracked.status === "succeeded") {
      let cancelled = false;
      void fetchCareerPath().then((next) => {
        if (cancelled || !next) return;
        setPath(next);
        setAutoBuilding(false);
        setActiveOpId(null);
        setPreferredTitle(next.prioritized_title ?? next.target_titles?.[0] ?? "");
      });
      return () => {
        cancelled = true;
      };
    }

    if (tracked.status === "failed" || tracked.status === "cancelled") {
      setAutoBuilding(false);
      setPathError(
        tracked.error_message?.trim() ||
          tracked.message.trim() ||
          "Couldn't build your path",
      );
    }
  }, [operations, path, activeOpId]);

  // ── Auto-build when no path exists (after restore settles) ─────────────────
  useEffect(() => {
    if (loadingPath || path || restoreState !== "ready") return;

    const existing = findActiveOperationByKind(
      operations,
      AI_OPERATION_KINDS.careerPathGenerate,
    );
    if (existing) {
      setActiveOpId(existing.id);
      setAutoBuilding(true);
      return;
    }

    let cancelled = false;
    setAutoBuilding(true);
    setPathError(null);
    void (async () => {
      try {
        const outcome = await generateCareerPath();
        if (cancelled) return;
        if (outcome.status === "accepted") {
          setActiveOpId(outcome.operation.operation_id);
        }
        const built = await resolveReadyOrAccepted(
          outcome,
          trackAndWait,
          async () => {
            const next = await fetchCareerPath();
            if (!next) throw new Error("No career path returned");
            return next;
          },
          { kind: AI_OPERATION_KINDS.careerPathGenerate },
        );
        if (!cancelled) {
          setPath(built);
          setPreferredTitle(
            built.prioritized_title ?? built.target_titles?.[0] ?? "",
          );
          setActiveOpId(null);
        }
      } catch (err) {
        if (!cancelled) {
          setPathError(
            err instanceof Error
              ? err.message
              : "Couldn't build your path",
          );
        }
      } finally {
        if (!cancelled) {
          setAutoBuilding(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // operations omitted: restore effect + restoreState gate cover active ops
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount/path/restore gate
  }, [loadingPath, path, restoreState, trackAndWait]);

  // ── Real-time refresh when profile updates in the background ───────────────
  useEffect(() => {
    if (!path) return;
    const id = window.setInterval(async () => {
      try {
        const next = await fetchCareerPath();
        if (!next) return;
        if (
          next.id !== path.id ||
          (next.updated_at && next.updated_at !== path.updated_at)
        ) {
          setPath(next);
          const pick = next.prioritized_title ?? next.target_titles?.[0] ?? preferredTitle;
          setPreferredTitle(pick);
        }
      } catch {
        // best-effort
      }
    }, 30_000);
    return () => window.clearInterval(id);
  }, [path, preferredTitle]);

  const applyPathResult = useCallback((next: CareerPath) => {
    setPath(next);
    setPreferredTitle(next.prioritized_title ?? next.target_titles?.[0] ?? "");
    setJobs([]);
    setSearched(false);
    setPathError(null);
    setActiveOpId(null);
    setAutoBuilding(false);
    setGenerating(false);
  }, []);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setPathError(null);
    try {
      const outcome = await generateCareerPath();
      if (outcome.status === "accepted") {
        setActiveOpId(outcome.operation.operation_id);
      }
      const next = await resolveReadyOrAccepted(
        outcome,
        trackAndWait,
        async () => {
          const fetched = await fetchCareerPath();
          if (!fetched) throw new Error("No career path returned");
          return fetched;
        },
        { kind: AI_OPERATION_KINDS.careerPathGenerate },
      );
      applyPathResult(next);
    } catch (err) {
      setPathError((err as Error).message ?? "Couldn't generate your path");
      setGenerating(false);
    }
  }, [applyPathResult, trackAndWait]);

  const handleRetryActive = useCallback(async () => {
    if (!activeOpId) return;
    setPathError(null);
    setAutoBuilding(true);
    try {
      const replacement = await retryOperation(activeOpId);
      setActiveOpId(replacement.id);
      const terminal = await waitForTrackedOperation(
        replacement,
        waitForOperation,
      );
      if (terminal.status !== "succeeded") {
        throw terminalOperationError(terminal);
      }
      const next = await fetchCareerPath();
      if (!next) throw new Error("No career path returned");
      applyPathResult(next);
    } catch (err) {
      setPathError(
        err instanceof Error ? err.message : "Couldn't generate your path",
      );
      setAutoBuilding(false);
    }
  }, [activeOpId, applyPathResult, retryOperation, waitForOperation]);

  const handleFindJobs = useCallback(async () => {
    setFindingJobs(true);
    setJobsError(null);
    try {
      const result = await findJobsForPath();
      setJobs(result.jobs);
      setRefreshing(result.refreshing);
      setSourceAvailable(result.source_available !== false);
      setSearched(true);
    } catch (err) {
      setJobsError((err as Error).message ?? "Couldn't find jobs");
    } finally {
      setFindingJobs(false);
    }
  }, []);

  const handleSavePreferred = useCallback(async () => {
    const title = preferredTitle.trim();
    if (!path || !title) return;
    if (savingPreferred) return;
    setSavingPreferred(true);
    setPathError(null);
    try {
      const existing = (path.target_titles ?? []).map((t) => t.trim()).filter(Boolean);
      const selection = [title, ...existing.filter((t) => t.toLowerCase() !== title.toLowerCase())];
      const updated = await prioritizeCareerPath(title, selection);
      setPath(updated);
      setPreferredTitle(updated.prioritized_title ?? title);
      // Changing the preferred direction changes the job universe — clear stale results.
      setJobs([]);
      setSearched(false);
      setRefreshing(false);
      setJobsError(null);
    } catch (err) {
      setPathError((err as Error).message ?? "Couldn't save your preferred path");
    } finally {
      setSavingPreferred(false);
    }
  }, [path, preferredTitle, savingPreferred]);

  const handleAddCustom = useCallback(() => {
    const t = customTitle.trim();
    if (!t) return;
    setPreferredTitle(t);
    setCustomTitle("");
  }, [customTitle]);

  // While the background Apify top-up runs, poll the find-jobs endpoint a few
  // times so fresher roles surface without a manual refresh.
  useEffect(() => {
    if (!refreshing) return;
    let attempts = 0;
    const id = window.setInterval(async () => {
      attempts += 1;
      try {
        const result = await findJobsForPath();
        setJobs(result.jobs);
      } catch {
        // best-effort — keep what we have
      }
      if (attempts >= 4) {
        setRefreshing(false);
        window.clearInterval(id);
      }
    }, 15_000);
    return () => window.clearInterval(id);
  }, [refreshing]);

  // ── First-load skeleton ───────────────────────────────────────────────────────
  if (loadingPath) {
    return (
      <div className={cn("p-5 space-y-3", className)}>
        <div className="h-24 rounded-xl bg-ink-100 animate-skeleton" />
        <div className="h-40 rounded-xl bg-ink-100 animate-skeleton" />
      </div>
    );
  }

  // ── No path yet → auto-building state (no manual click) ────────────────────
  if (!path) {
    return (
      <div className={cn("p-5", className)}>
        <Card>
          <CardBody>
            <div className="flex flex-col items-center gap-4 py-6 text-center">
              <div className="w-14 h-14 rounded-2xl bg-ink-100 flex items-center justify-center">
                {autoBuilding || generating ? (
                  <Loader2
                    className="h-7 w-7 text-accent animate-spin"
                    strokeWidth={1.5}
                  />
                ) : (
                  <Route className="h-7 w-7 text-ink-500" strokeWidth={1.5} />
                )}
              </div>
              <div className="space-y-1">
                <p className="text-small font-semibold text-ink-900">
                  {autoBuilding || generating
                    ? "Mapping your career path…"
                    : "Your career path is on the way"}
                </p>
                <p className="text-micro text-ink-500 max-w-xs">
                  Aarya reads your profile and maps where you are today to where
                  you can go next — this updates automatically as your profile
                  grows.
                </p>
              </div>
              {!autoBuilding && !generating && pathError && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleGenerate()}
                  leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
                >
                  Try again
                </Button>
              )}
              {pathError && (
                <p className="text-micro text-destructive">{pathError}</p>
              )}
              {activeOpId && operations[activeOpId] ? (
                <div className="w-full max-w-sm text-left">
                  <AiOperationProgress
                    compact
                    operation={operations[activeOpId]}
                    onCancel={() => {
                      void cancelOperation(activeOpId).catch(() => undefined);
                    }}
                    onRetry={() => {
                      void handleRetryActive();
                    }}
                  />
                </div>
              ) : null}
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  // ── Path present ────────────────────────────────────────────────────────────────
  return (
    <div className={cn("flex flex-col h-full", className)}>
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {/* ── Path summary + timeline ──────────────────────────────────── */}
        <Card>
          <CardBody className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-xl bg-ink-900 flex items-center justify-center shrink-0">
                <Route className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
              </div>
              <div className="min-w-0">
                <p className="text-small font-semibold text-ink-900">
                  {path.current_role
                    ? `Your path from ${path.current_role}`
                    : "Your career path"}
                </p>
                {path.summary && (
                  <p className="text-micro text-ink-600 leading-relaxed mt-1">
                    {path.summary}
                  </p>
                )}
              </div>
            </div>

            {/* Timeline */}
            {path.steps.length > 0 && (
              <ol className="space-y-0">
                {path.steps.map((step, i) => (
                  <StepRow
                    key={`${step.title}-${i}`}
                    step={step}
                    last={i === path.steps.length - 1}
                  />
                ))}
              </ol>
            )}

            {/* Target-role chips */}
            {path.target_titles.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                  Roles to search now
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {path.target_titles.map((title) => (
                    <Badge key={title} tone="accent">
                      {title}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Preferred path selector */}
            <div className="space-y-2 pt-1">
              <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                Preferred path
              </span>
              <p className="text-micro text-ink-500 leading-relaxed">
                Pick the one direction you want to prioritise. We’ll still search similar titles,
                but this becomes your main track for matching and intros.
              </p>

              <div className="flex flex-wrap gap-1.5">
                {path.target_titles.map((title) => {
                  const active = preferredTitle?.toLowerCase() === title.toLowerCase();
                  return (
                    <button
                      key={title}
                      type="button"
                      onClick={() => setPreferredTitle(title)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-micro font-semibold transition-colors",
                        active
                          ? "border-ink-900 bg-ink-900 text-paper-0"
                          : "border-ink-200 bg-paper-0 text-ink-700 hover:border-ink-400",
                      )}
                      aria-pressed={active}
                    >
                      {title}
                    </button>
                  );
                })}
                {preferredTitle &&
                  path.target_titles.every(
                    (t) => t.toLowerCase() !== preferredTitle.toLowerCase(),
                  ) && (
                    <span className="rounded-full border border-ink-900 bg-ink-900 text-paper-0 px-3 py-1 text-micro font-semibold">
                      {preferredTitle}
                    </span>
                  )}
              </div>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={customTitle}
                  onChange={(e) => setCustomTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddCustom();
                    }
                  }}
                  placeholder="Or type your own (e.g., Growth Manager)"
                  className="flex-1 rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent-ring"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleAddCustom()}
                  disabled={!customTitle.trim()}
                >
                  Add
                </Button>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleSavePreferred()}
                  loading={savingPreferred}
                  disabled={!preferredTitle.trim() || savingPreferred}
                >
                  Save preferred path
                </Button>
                {path.prioritized_title && (
                  <span className="text-micro text-ink-400">
                    Current: {path.prioritized_title}
                  </span>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleFindJobs()}
                loading={findingJobs}
                leftIcon={<Search className="h-3.5 w-3.5" strokeWidth={1.5} />}
              >
                {findingJobs ? "Finding jobs…" : "Find jobs for this path"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void handleGenerate()}
                loading={generating}
                leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
              >
                Regenerate
              </Button>
            </div>
            {pathError && (
              <p className="text-micro text-destructive">{pathError}</p>
            )}
          </CardBody>
        </Card>

        {/* ── Jobs along the path ──────────────────────────────────────── */}
        {refreshing && (
          <div className="flex items-center gap-2 text-small text-ink-500 px-1">
            <Loader2 className="h-4 w-4 animate-spin text-accent" strokeWidth={1.5} />
            Aarya is scanning fresh roles for your path…
          </div>
        )}

        {jobsError && (
          <EmptyState
            icon={<AlertCircle strokeWidth={1.5} />}
            title="Couldn't find jobs"
            description={jobsError}
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleFindJobs()}
              >
                Try again
              </Button>
            }
          />
        )}

        {searched && !jobsError && jobs.length === 0 && !refreshing && !sourceAvailable && (
          <EmptyState
            icon={<AlertCircle strokeWidth={1.5} />}
            title="Job search is temporarily unavailable"
            description="Aarya can't reach the job source right now. This is usually a configuration issue on our side, not a lack of roles — please try again shortly."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void handleFindJobs()}
              >
                Try again
              </Button>
            }
          />
        )}

        {searched && !jobsError && jobs.length === 0 && !refreshing && sourceAvailable && (
          <EmptyState
            icon={<Search strokeWidth={1.5} />}
            title="No matches yet"
            description="Aarya is pulling fresh roles for your path. Check back in a minute or two."
          />
        )}

        {jobs.length > 0 && (
          <div className="space-y-3">
            {jobs.map((job) => (
              <JobCard
                key={job.job_id}
                job={job}
                conversationId={conversationId}
                onRequestIntro={onRequestIntro}
                onDirectApply={onDirectApply}
                onTailorResume={handlePrepareKit}
                tailorStatus={kitByJob[job.job_id] ?? "idle"}
                onOpenKitPreview={openKitPreview}
                onLearningRoadmap={handleLearningRoadmap}
                roadmapStatus={roadmapByJob[job.job_id] ?? "idle"}
                isSaved={savedJobIds.has(job.job_id)}
                onSavedChange={onSavedChange}
              />
            ))}
          </div>
        )}
      </div>

      <ResumePreviewModal
        open={!!preview}
        onClose={closePreview}
        resumeId={preview?.resumeId ?? null}
        jobId={preview?.jobId ?? null}
        jobTitle={preview?.jobTitle}
        initialTab={preview?.tab}
      />
    </div>
  );
}

// ── Timeline step ───────────────────────────────────────────────────────────────

function StepRow({ step, last }: { step: CareerStep; last: boolean }) {
  const meta = LEVEL_META[step.level] ?? LEVEL_META.next;
  return (
    <li className="relative flex gap-3 pb-3 last:pb-0">
      {/* Rail */}
      <div className="flex flex-col items-center pt-1">
        <span
          className={cn(
            "w-2.5 h-2.5 rounded-full ring-4 shrink-0",
            meta.dot,
            meta.ring
          )}
        />
        {!last && <span className="w-px flex-1 bg-ink-100 mt-1" />}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-small font-semibold text-ink-900">{step.title}</p>
          <span className="text-micro text-ink-400">{meta.label}</span>
          {step.timeframe && (
            <span className="text-micro text-ink-400">· {step.timeframe}</span>
          )}
        </div>
        {step.rationale && (
          <p className="text-micro text-ink-500 leading-snug mt-0.5">
            {step.rationale}
          </p>
        )}
        {step.skills_to_build.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 mt-1.5">
            {step.skills_to_build.map((skill) => (
              <span
                key={skill}
                className="text-micro text-ink-600 bg-ink-50 px-2 py-0.5 rounded-sm"
              >
                {skill}
              </span>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
