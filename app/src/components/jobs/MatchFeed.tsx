"use client";

/**
 * MatchFeed — DESIGN.md compliant feed of matched jobs.
 *
 *   - Filter bar (min score slider, remote toggle, seniority select)
 *   - List of <JobCard>
 *   - Skeleton on first load
 *   - <EmptyState> when no matches
 *   - <Button variant="ghost"> for "Load more"
 *
 * All chrome through primitives. No bespoke styling beyond layout.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, RefreshCw, SlidersHorizontal } from "@/components/brand/icons";
import { cn } from "@/lib/utils";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeed,
  fetchMatchFeedCount,
  fetchMatchHistory,
  fetchMatchTriage,
  findNewMatches,
  getCachedMatchFeed,
  getCachedMatchFeedCount,
  MATCH_FEED_INVALIDATE_EVENT,
  MATCH_FEED_PAGE_SIZE,
  MATCH_FEED_RELEVANCE_FLOOR,
  type MatchedJob,
  type MatchFeedFilters,
} from "@/lib/api/matches";
import { dedupeJobs } from "@/lib/chat/dedupeJobs";
import { useJobCardAssets } from "@/hooks/useJobCardAssets";
import { ResumePreviewModal } from "@/components/resumes/ResumePreviewModal";
import { Button, Card, EmptyState, Select } from "@/components/ui";
import { Stagger, StaggerItem } from "@/components/ui/motion";
import { JobCard } from "./JobCard";
import { MatchesEmptyPanel } from "./MatchesEmptyPanel";

interface MatchFeedProps {
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  onDirectApply?: (job: MatchedJob) => void;
  applyLocked?: boolean;
  /** Shows a "Based on LinkedIn" hint when matches predate a resume upload. */
  matchSourceBadge?: "linkedin";
  savedJobIds?: Set<string>;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  onAskAarya?: () => void;
  seedJobs?: MatchedJob[] | null;
  seedTitle?: string | null;
  /** Sidebar drawer: flat list, no filters/tiers/pagination. */
  compact?: boolean;
  className?: string;
}

const SENIORITY_OPTIONS = [
  { value: "", label: "All levels" },
  { value: "intern", label: "Intern" },
  { value: "junior", label: "Junior" },
  { value: "mid", label: "Mid-level" },
  { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" },
  { value: "director", label: "Director" },
];

const PAGE_SIZE = MATCH_FEED_PAGE_SIZE;

function formatHistoryDate(job: MatchedJob): string | null {
  const raw = job.last_seen_at ?? job.first_seen_at ?? job.computed_at;
  if (!raw) return null;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function historyDateLabel(job: MatchedJob): string | null {
  const formatted = formatHistoryDate(job);
  if (!formatted) return null;
  if (job.last_seen_at) return `Last seen ${formatted}`;
  if (job.first_seen_at) return `First seen ${formatted}`;
  return `Matched ${formatted}`;
}

// Confidence tiers (mirrors the backend ranking thresholds). Grouping the feed
// into these sections is what makes the first screen read as *curated* rather
// than a flat wall of percentages.
const TIER_ORDER = ["strong", "good", "worth_a_look", "exploratory"] as const;
const TIER_META: Record<string, { label: string; description: string }> = {
  strong: { label: "Strong matches", description: "High-confidence fits — start here." },
  good: { label: "Good matches", description: "Solid alignment with your profile." },
  worth_a_look: { label: "Worth a look", description: "Promising, with a few gaps." },
  exploratory: { label: "Exploratory", description: "A stretch — if you're curious." },
};
const MORE_SECTION = { key: "_more", label: "More matches", description: "" };

type FeedSection = { key: string; label: string; description: string; jobs: MatchedJob[] };

const NEW_SECTION: FeedSection = {
  key: "_new_for_you",
  label: "New for you",
  description: "Fresh roles you haven’t seen before.",
  jobs: [],
};

const SINCE_VISIT_SECTION: FeedSection = {
  key: "_since_visit",
  label: "New since your last visit",
  description: "Posted or ranked since you were last here.",
  jobs: [],
};

/** Group jobs into ordered confidence-tier sections; untiered (load-more) last. */
function groupByTier(jobs: MatchedJob[]): FeedSection[] {
  const buckets = new Map<string, MatchedJob[]>();
  for (const job of jobs) {
    const key = job.tier && TIER_META[job.tier] ? job.tier : MORE_SECTION.key;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(job);
    else buckets.set(key, [job]);
  }
  const sections: FeedSection[] = [];
  for (const key of TIER_ORDER) {
    const items = buckets.get(key);
    if (items?.length) sections.push({ key, ...TIER_META[key], jobs: items });
  }
  const more = buckets.get(MORE_SECTION.key);
  if (more?.length) sections.push({ ...MORE_SECTION, jobs: more });
  return sections;
}

function groupWithNewSection(jobs: MatchedJob[], options: { enabled: boolean }): FeedSection[] {
  if (!options.enabled) return groupByTier(jobs);
  const sinceVisit = jobs.filter((j) => Boolean(j.is_new_since_visit));
  const fresh = jobs.filter((j) => Boolean(j.is_new_for_you) && !j.is_new_since_visit);
  const rest = jobs.filter((j) => !j.is_new_for_you && !j.is_new_since_visit);
  const out: FeedSection[] = [];
  if (sinceVisit.length) out.push({ ...SINCE_VISIT_SECTION, jobs: sinceVisit });
  if (fresh.length) out.push({ ...NEW_SECTION, jobs: fresh });
  out.push(...groupByTier(rest));
  return out;
}

function applyLocalFilters(
  jobs: MatchedJob[],
  filters: { remoteOnly: boolean; seniority: string }
): MatchedJob[] {
  let visible = jobs;
  if (filters.remoteOnly) visible = visible.filter((j) => j.is_remote);
  if (filters.seniority) {
    visible = visible.filter((j) => j.seniority === filters.seniority);
  }
  return visible;
}

export function MatchFeed({
  conversationId,
  onRequestIntro,
  onDirectApply,
  applyLocked = false,
  matchSourceBadge,
  savedJobIds = new Set(),
  onSavedChange,
  onAskAarya,
  seedJobs,
  seedTitle,
  compact = false,
  className,
}: MatchFeedProps) {
  const pageSize = compact ? 12 : PAGE_SIZE;
  const initialJobs = getCachedMatchFeed(DEFAULT_MATCH_FEED_FILTERS);
  const [jobs, setJobs] = useState<MatchedJob[]>(initialJobs ?? []);
  const [totalCount, setTotalCount] = useState<number | null>(
    () => getCachedMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS)
  );
  const [loading, setLoading] = useState(initialJobs === null && !seedJobs?.length);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(
    compact ? false : (initialJobs?.length ?? PAGE_SIZE) === PAGE_SIZE,
  );
  const [offset, setOffset] = useState(initialJobs?.length ?? 0);
  const [emptyRefreshCount, setEmptyRefreshCount] = useState(0);
  const [triageJobs, setTriageJobs] = useState<MatchedJob[]>([]);
  const [triageLoading, setTriageLoading] = useState(false);
  const [historyJobs, setHistoryJobs] = useState<MatchedJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [findingNew, setFindingNew] = useState(false);
  const [findNewMessage, setFindNewMessage] = useState<string | null>(null);
  const [refreshingNew, setRefreshingNew] = useState(false);

  // Filters
  const [minScore, setMinScore] = useState(MATCH_FEED_RELEVANCE_FLOOR);
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [seniority, setSeniority] = useState("");
  const [showFilters, setShowFilters] = useState(false);

  const {
    kitByJob,
    roadmapByJob,
    preview,
    openKitPreview,
    closePreview,
    handlePrepareKit,
    handleLearningRoadmap,
  } = useJobCardAssets();

  const load = useCallback(
    async (reset = false, scoreFloor = minScore) => {
      const currentOffset = reset ? 0 : offset;
      const isFirst = reset || currentOffset === 0;

      setError(null);

      try {
        const filters: MatchFeedFilters = {
          min_score: scoreFloor,
          limit: pageSize,
          offset: currentOffset,
        };

        const cached = isFirst ? getCachedMatchFeed(filters) : null;
        if (cached) {
          setJobs(applyLocalFilters(cached, { remoteOnly, seniority }));
          setHasMore(compact ? false : cached.length === pageSize);
          setOffset(currentOffset + cached.length);
          setLoading(false);
          // Refresh in the background without blocking the sidebar.
          void fetchMatchFeed(filters, { force: true })
            .then((rawData) => {
              const data = applyLocalFilters(rawData, { remoteOnly, seniority });
              setJobs(data);
              setHasMore(compact ? false : rawData.length === pageSize);
              setOffset(rawData.length);
              if (data.length > 0) setEmptyRefreshCount(0);
            })
            .catch(() => {
              /* keep cached rows visible */
            });
          return;
        } else if (isFirst) {
          setLoading(true);
        } else {
          setLoadingMore(true);
        }

        const rawData = await fetchMatchFeed(filters);
        const data = applyLocalFilters(rawData, { remoteOnly, seniority });

        if (isFirst && data.length === 0 && scoreFloor > 0.25) {
          return load(true, 0.25);
        }

        setJobs((prev) => (isFirst ? data : [...prev, ...data]));
        if (isFirst && data.length > 0) setEmptyRefreshCount(0);
        setHasMore(compact ? false : rawData.length === pageSize);
        setOffset(currentOffset + rawData.length);
      } catch (err) {
        const hasBlockingData =
          isFirst &&
          getCachedMatchFeed({
            min_score: minScore,
            limit: pageSize,
            offset: currentOffset,
          }) !== null;

        if (!hasBlockingData) {
          setError((err as Error).message ?? "Failed to load matches");
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [minScore, remoteOnly, seniority, offset, compact, pageSize]
  );

  useEffect(() => {
    let cancelled = false;
    fetchMatchFeedCount({ min_score: minScore })
      .then((total) => {
        if (!cancelled) setTotalCount(total);
      })
      .catch(() => {
        if (!cancelled) setTotalCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [minScore]);

  useEffect(() => {
    if (compact || seedJobs?.length) return;
    let cancelled = false;
    setTriageLoading(true);
    fetchMatchTriage(10)
      .then((data) => {
        if (!cancelled) setTriageJobs(data);
      })
      .catch(() => {
        if (!cancelled) setTriageJobs([]);
      })
      .finally(() => {
        if (!cancelled) setTriageLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [compact, seedJobs?.length]);

  useEffect(() => {
    if (!compact) return;
    let cancelled = false;
    setHistoryLoading(true);
    fetchMatchHistory({ min_score: 0, limit: 100 })
      .then((data) => {
        if (!cancelled) setHistoryJobs(data);
      })
      .catch(() => {
        if (!cancelled) setHistoryJobs([]);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Re-pull when chat seeds new jobs so Job history catches persisted rows.
  }, [compact, seedJobs?.length]);

  const handleFindNewJobs = useCallback(async () => {
    setFindingNew(true);
    setFindNewMessage(null);
    setError(null);
    try {
      const result = await findNewMatches();
      setFindNewMessage(result.message);
      setRefreshingNew(result.refreshing);
      if (result.jobs.length > 0) {
        setJobs((prev) => dedupeJobs([...result.jobs, ...prev]));
        setEmptyRefreshCount(0);
      }
      const history = await fetchMatchHistory({ min_score: 0, limit: 100 });
      setHistoryJobs(history);
      void fetchMatchFeed(DEFAULT_MATCH_FEED_FILTERS, { force: true }).catch(() => undefined);
    } catch (err) {
      setError((err as Error).message ?? "Couldn't find new jobs");
    } finally {
      setFindingNew(false);
    }
  }, []);

  useEffect(() => {
    if (!refreshingNew) return;
    let attempts = 0;
    const id = window.setInterval(async () => {
      attempts += 1;
      try {
        const result = await findNewMatches();
        if (result.jobs.length > 0) {
          setJobs((prev) => dedupeJobs([...result.jobs, ...prev]));
          setEmptyRefreshCount(0);
        }
        setFindNewMessage(result.message);
        if (!result.refreshing || attempts >= 6) {
          setRefreshingNew(false);
          const history = await fetchMatchHistory({ min_score: 0, limit: 100 });
          setHistoryJobs(history);
        }
      } catch {
        if (attempts >= 6) setRefreshingNew(false);
      }
    }, 12_000);
    return () => window.clearInterval(id);
  }, [refreshingNew]);

  useEffect(() => {
    setOffset(0);
    setHasMore(true);
    setEmptyRefreshCount(0);
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minScore, remoteOnly, seniority]);

  useEffect(() => {
    const onInvalidate = () => {
      // Resume upload and profile edits invalidate the match feed cache, but
      // React state must be explicitly reset so the sidebar doesn't get stuck
      // showing zero matches.
      setError(null);
      setJobs([]);
      setOffset(0);
      setHasMore(true);
      setEmptyRefreshCount(0);
      void fetchMatchFeedCount({ min_score: minScore }, { force: true })
        .then((total) => setTotalCount(total))
        .catch(() => setTotalCount(null));
      void load(true);
    };

    if (typeof window === "undefined") return;
    window.addEventListener(MATCH_FEED_INVALIDATE_EVENT, onInvalidate);
    return () =>
      window.removeEventListener(MATCH_FEED_INVALIDATE_EVENT, onInvalidate);
  }, [load]);

  useEffect(() => {
    if (loading || error || jobs.length > 0 || emptyRefreshCount >= 5) return;
    const id = window.setTimeout(() => {
      setEmptyRefreshCount((count) => count + 1);
      void load(true);
    }, 12_000);
    return () => window.clearTimeout(id);
  }, [emptyRefreshCount, error, jobs.length, load, loading]);

  // Merge chat/kickoff seed jobs on top of the live feed (deduped) so anything
  // Aarya showed in chat appears here immediately, while the feed still loads.
  const displayJobs = applyLocalFilters(
    seedJobs?.length ? dedupeJobs([...seedJobs, ...jobs]) : jobs,
    { remoteOnly, seniority },
  );
  const visibleCount = displayJobs.length;
  const sections = groupWithNewSection(displayJobs, { enabled: !compact && offset <= pageSize });
  // Hide headers when the only section is the untiered "More" bucket (e.g. the
  // backend didn't curate this page) — a lone "More matches" header reads oddly.
  const showHeaders =
    !compact &&
    (sections.length > 1 || (sections.length === 1 && sections[0].key !== MORE_SECTION.key));
  const hasLocalFilters = remoteOnly || Boolean(seniority);
  const countLabel = (() => {
    if (loading && visibleCount === 0) return "";
    if (hasLocalFilters || seedJobs?.length) {
      return `${visibleCount} match${visibleCount !== 1 ? "es" : ""} shown`;
    }
    if (totalCount !== null) {
      return `${totalCount} match${totalCount !== 1 ? "es" : ""}`;
    }
    return `${visibleCount} match${visibleCount !== 1 ? "es" : ""}`;
  })();

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {compact ? (
        <div className="mb-3 shrink-0 space-y-2">
          <div className="flex items-center justify-between gap-2">
            {countLabel ? (
              <p className="text-micro text-ink-500">{countLabel}</p>
            ) : (
              <span />
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleFindNewJobs()}
              loading={findingNew || refreshingNew}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
              className="shrink-0"
            >
              Find new jobs
            </Button>
          </div>
          {findNewMessage ? (
            <p className="text-micro text-ink-500">{findNewMessage}</p>
          ) : null}
        </div>
      ) : countLabel ? (
        <p className="text-micro text-ink-500 mb-3 shrink-0">{countLabel}</p>
      ) : null}
      {matchSourceBadge === "linkedin" && (
        <p className="text-micro text-ink-500 mb-3 shrink-0">
          Based on LinkedIn — upload a CV to sharpen scores.
        </p>
      )}
      {seedJobs?.length && !compact ? (
        <p className="text-micro text-ink-500 mb-3 shrink-0">
          {seedTitle
            ? `Including Aarya's jobs for ${seedTitle}.`
            : "Including the roles Aarya just found in chat."}
        </p>
      ) : null}
      {/* ── Filter bar (full feed only) ─────────────────────────────── */}
      {!compact &&
      (() => {
        const activeFilterCount =
          (remoteOnly ? 1 : 0) +
          (seniority ? 1 : 0) +
          (minScore !== MATCH_FEED_RELEVANCE_FLOOR ? 1 : 0);
        return (
          <div className="pb-4 mb-4 border-b border-ink-100 shrink-0">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setShowFilters((v) => !v)}
                className={cn(
                  "flex items-center gap-1.5 text-small px-3 py-1.5 rounded-full border transition-colors duration-fast",
                  showFilters || activeFilterCount > 0
                    ? "border-ink-300 text-ink-900"
                    : "border-ink-100 text-ink-500 hover:text-ink-900 hover:border-ink-300"
                )}
                aria-expanded={showFilters}
              >
                <SlidersHorizontal className="h-3.5 w-3.5" strokeWidth={1.5} />
                Filters
                {activeFilterCount > 0 && (
                  <span className="min-w-[1.25rem] h-5 px-1 rounded-full bg-ink-900 text-micro font-medium text-paper-0 flex items-center justify-center">
                    {activeFilterCount}
                  </span>
                )}
              </button>
              <span className="ml-auto text-small text-ink-500">{countLabel}</span>
            </div>

            {showFilters && (
              <div className="flex flex-wrap items-center gap-3 mt-3 animate-fade-in">
                {/* Min score */}
                <div className="flex items-center gap-2">
                  <span className="text-small text-ink-500 whitespace-nowrap">
                    Min match
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={80}
                    step={10}
                    value={minScore * 100}
                    onChange={(e) => setMinScore(Number(e.target.value) / 100)}
                    className="w-24 accent-accent"
                    aria-label="Minimum match score"
                  />
                  <span className="text-small font-medium text-ink-900 w-8">
                    {Math.round(minScore * 100)}%
                  </span>
                </div>

                {/* Remote toggle */}
                <button
                  type="button"
                  onClick={() => setRemoteOnly((v) => !v)}
                  className={cn(
                    "flex items-center gap-1.5 text-small px-3 py-1.5 rounded-full border transition-colors duration-fast",
                    remoteOnly
                      ? "bg-ink-900 text-paper-0 border-ink-900 font-medium"
                      : "border-ink-100 text-ink-500 hover:text-ink-900 hover:border-ink-300"
                  )}
                  aria-pressed={remoteOnly}
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      remoteOnly ? "bg-paper-0" : "bg-ink-300"
                    )}
                  />
                  Remote only
                </button>

                {/* Seniority */}
                <Select
                  value={seniority}
                  onChange={(e) => setSeniority(e.target.value)}
                  options={SENIORITY_OPTIONS}
                  className="text-small h-8 py-0 rounded-full px-3 w-auto"
                  aria-label="Seniority filter"
                />
              </div>
            )}
          </div>
        );
      })()}

      {/* ── Content ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1 pb-6">
        {loading &&
          visibleCount === 0 &&
          Array.from({ length: 4 }).map((_, i) => <JobCardSkeleton key={i} />)}

        {!loading && error && visibleCount === 0 && (
          <EmptyState
            icon={<AlertCircle strokeWidth={1.5} />}
            title="Couldn't load matches"
            description={error}
            action={
              <Button variant="secondary" size="sm" onClick={() => load(true)}>
                Try again
              </Button>
            }
          />
        )}

        {!loading && !error && visibleCount === 0 && historyJobs.length === 0 && !historyLoading && (
          <MatchesEmptyPanel
            onAskAarya={onAskAarya}
            isSearching={emptyRefreshCount < 5}
          />
        )}

        {!loading && !error && visibleCount === 0 && (historyLoading || historyJobs.length > 0) && (
          <p className="text-micro text-ink-500 mb-2">
            No new matches right now — your past jobs are below.
          </p>
        )}

        {!compact && !loading && triageJobs.length > 0 && (
          <div className="space-y-3 mb-4">
            <div className="flex items-baseline justify-between pt-1">
              <h4 className="text-small font-semibold text-ink-900">
                Aarya&apos;s top picks
                <span className="ml-1.5 text-ink-300 font-normal">{triageJobs.length}</span>
              </h4>
            </div>
            {triageLoading ? (
              <JobCardSkeleton />
            ) : (
              <Stagger className="space-y-3">
                {triageJobs.map((job) => (
                  <StaggerItem key={`triage-${job.job_id}`}>
                    <JobCard
                      job={job}
                      conversationId={conversationId}
                      onRequestIntro={onRequestIntro}
                      onDirectApply={onDirectApply}
                      applyLocked={applyLocked}
                      onTailorResume={handlePrepareKit}
                      tailorStatus={kitByJob[job.job_id] ?? "idle"}
                      onOpenKitPreview={openKitPreview}
                      onLearningRoadmap={handleLearningRoadmap}
                      roadmapStatus={roadmapByJob[job.job_id] ?? "idle"}
                      isSaved={savedJobIds.has(job.job_id)}
                      onSavedChange={onSavedChange}
                    />
                  </StaggerItem>
                ))}
              </Stagger>
            )}
          </div>
        )}

        {visibleCount > 0 &&
          sections.map((section) => (
            <div key={section.key} className="space-y-3">
              {showHeaders && (
                <div className="pt-1">
                  <h4 className="text-small font-semibold text-ink-900">
                    {section.label}
                    <span className="ml-1.5 text-ink-300 font-normal">
                      {section.jobs.length}
                    </span>
                  </h4>
                </div>
              )}
              <Stagger className="space-y-3">
                {section.jobs.map((job) => (
                  <StaggerItem key={job.job_id}>
                    <JobCard
                      job={job}
                      conversationId={conversationId}
                      onRequestIntro={onRequestIntro}
                      onDirectApply={
                        onDirectApply ??
                        ((j) => {
                          if (j.apply_url) {
                            window.open(j.apply_url, "_blank", "noopener,noreferrer");
                          }
                        })
                      }
                      applyLocked={applyLocked}
                      onTailorResume={handlePrepareKit}
                      tailorStatus={kitByJob[job.job_id] ?? "idle"}
                      onOpenKitPreview={openKitPreview}
                      onLearningRoadmap={handleLearningRoadmap}
                      roadmapStatus={roadmapByJob[job.job_id] ?? "idle"}
                      isSaved={savedJobIds.has(job.job_id)}
                      onSavedChange={onSavedChange}
                    />
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          ))}

        {!loading && !error && hasMore && jobs.length > 0 && !seedJobs?.length && !compact && (
          <div className="pt-2">
            <Button
              variant="ghost"
              size="md"
              onClick={() => load(false)}
              loading={loadingMore}
              fullWidth
            >
              {loadingMore ? "Loading…" : "Load more matches"}
            </Button>
          </div>
        )}

        {compact ? (
          <div className="mt-2 space-y-3">
            <div className="flex items-baseline justify-between">
              <h4 className="text-small font-semibold text-ink-900">
                Job history
                {!historyLoading && (
                  <span className="ml-1.5 text-ink-300 font-normal">
                    {historyJobs.length}
                  </span>
                )}
              </h4>
              <span className="text-micro text-ink-400">Newest first</span>
            </div>
            {historyLoading ? (
              <JobCardSkeleton />
            ) : historyJobs.length > 0 ? (
              <Stagger className="space-y-3">
                {historyJobs.map((job) => (
                  <StaggerItem key={`history-${job.job_id}`}>
                    <JobCard
                      job={job}
                      conversationId={conversationId}
                      onRequestIntro={onRequestIntro}
                      onDirectApply={onDirectApply}
                      applyLocked={applyLocked}
                      onTailorResume={handlePrepareKit}
                      tailorStatus={kitByJob[job.job_id] ?? "idle"}
                      onOpenKitPreview={openKitPreview}
                      onLearningRoadmap={handleLearningRoadmap}
                      roadmapStatus={roadmapByJob[job.job_id] ?? "idle"}
                      isSaved={savedJobIds.has(job.job_id)}
                      onSavedChange={onSavedChange}
                      historyDateLabel={historyDateLabel(job)}
                    />
                  </StaggerItem>
                ))}
              </Stagger>
            ) : (
              <p className="text-micro text-ink-500 pb-2">
                Past matches will show here once Aarya has scored roles for you.
              </p>
            )}
          </div>
        ) : null}
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

// ── Skeleton ────────────────────────────────────────────────────────────────

function JobCardSkeleton() {
  return (
    <Card className="p-5">
      <div className="animate-skeleton">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-9 h-9 rounded-full bg-ink-100 shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 bg-ink-100 rounded w-1/3" />
            <div className="h-4 bg-ink-100 rounded w-2/3" />
          </div>
          <div className="w-12 h-4 bg-ink-100 rounded-full" />
        </div>
        <div className="flex gap-1.5 mb-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-5 w-16 bg-ink-100 rounded-sm" />
          ))}
        </div>
        <div className="flex gap-1 mb-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-4 w-12 bg-ink-100 rounded-sm" />
          ))}
        </div>
        <div className="h-3 bg-ink-100 rounded w-full mb-1" />
        <div className="h-3 bg-ink-100 rounded w-3/4 mb-4" />
        <div className="flex gap-2 pt-3 border-t border-ink-100">
          <div className="flex-1 h-8 bg-ink-100 rounded-md" />
          <div className="flex-1 h-8 bg-ink-100 rounded-md" />
          <div className="flex-1 h-8 bg-ink-100 rounded-md" />
          <div className="w-8 h-8 bg-ink-100 rounded-md" />
        </div>
      </div>
    </Card>
  );
}
