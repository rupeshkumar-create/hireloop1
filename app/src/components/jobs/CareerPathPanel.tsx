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
  type CareerPath,
  type CareerStep,
} from "@/lib/api/career";
import type { MatchedJob } from "@/lib/api/matches";
import {
  openTailoredDownload,
  pollTailoredResume,
  requestTailoredResume,
} from "@/lib/api/tailored";
import { Badge, Button, Card, CardBody, EmptyState } from "@/components/ui";
import { JobCard } from "./JobCard";

interface CareerPathPanelProps {
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
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
  savedJobIds = new Set(),
  onSavedChange,
  className,
}: CareerPathPanelProps) {
  const [path, setPath] = useState<CareerPath | null>(null);
  const [loadingPath, setLoadingPath] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [autoBuilding, setAutoBuilding] = useState(false);
  const [pathError, setPathError] = useState<string | null>(null);

  const [jobs, setJobs] = useState<MatchedJob[]>([]);
  const [findingJobs, setFindingJobs] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [sourceAvailable, setSourceAvailable] = useState(true);

  // Per-job tailored-resume state (mirrors MatchFeed).
  const [tailorByJob, setTailorByJob] = useState<
    Record<string, "idle" | "loading" | "ready" | "error">
  >({});

  // ── Load the latest path on mount ────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    fetchCareerPath()
      .then((p) => {
        if (!cancelled) setPath(p);
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

  // ── Auto-build: kick off generation + poll until ready ─────────────────────
  useEffect(() => {
    if (loadingPath || path) return;

    setAutoBuilding(true);
    setPathError(null);
    let attempts = 0;
    let cancelled = false;
    let generateStarted = false;

    const kickOffBuild = async () => {
      if (generateStarted) return;
      generateStarted = true;
      try {
        const built = await generateCareerPath();
        if (!cancelled) setPath(built);
      } catch {
        // Backend hooks may still build in the background — keep polling.
      }
    };

    const poll = async () => {
      try {
        const next = await fetchCareerPath();
        if (cancelled) return true;
        if (next) {
          setPath(next);
          setAutoBuilding(false);
          return true;
        }
      } catch (err) {
        if (!cancelled) {
          setPathError((err as Error).message ?? "Couldn't load your path");
        }
      }
      return false;
    };

    void kickOffBuild();
    void poll();
    const id = window.setInterval(async () => {
      attempts += 1;
      const ready = await poll();
      if (ready || attempts >= 30) {
        window.clearInterval(id);
        if (!cancelled) {
          setAutoBuilding(false);
          if (!ready && attempts >= 30) {
            setPathError(
              "Aarya is still building your path. Check back in a moment or regenerate."
            );
          }
        }
      }
    }, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [loadingPath, path]);

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
        }
      } catch {
        // best-effort
      }
    }, 30_000);
    return () => window.clearInterval(id);
  }, [path]);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setPathError(null);
    try {
      const next = await generateCareerPath();
      setPath(next);
      // A regenerated path may target different roles — clear stale results.
      setJobs([]);
      setSearched(false);
    } catch (err) {
      setPathError((err as Error).message ?? "Couldn't generate your path");
    } finally {
      setGenerating(false);
    }
  }, []);

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
      if (!resumeId) throw new Error(started.message ?? "No resume id returned");
      const ready = await pollTailoredResume(resumeId);
      openTailoredDownload(ready.id);
      setTailorByJob((s) => ({ ...s, [job.job_id]: "ready" }));
    } catch {
      setTailorByJob((s) => ({ ...s, [job.job_id]: "error" }));
    }
  }, []);

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
                onDirectApply={(j) => {
                  if (j.apply_url)
                    window.open(j.apply_url, "_blank", "noopener,noreferrer");
                }}
                onTailorResume={handleTailorResume}
                tailorStatus={tailorByJob[job.job_id] ?? "idle"}
                isSaved={savedJobIds.has(job.job_id)}
                onSavedChange={onSavedChange}
              />
            ))}
          </div>
        )}
      </div>
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
