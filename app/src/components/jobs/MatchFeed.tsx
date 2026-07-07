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
import { AlertCircle, SlidersHorizontal } from "@/components/brand/icons";
import { cn } from "@/lib/utils";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeed,
  fetchMatchFeedCount,
  getCachedMatchFeed,
  getCachedMatchFeedCount,
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
  className,
}: MatchFeedProps) {
  const initialJobs = getCachedMatchFeed(DEFAULT_MATCH_FEED_FILTERS);
  const [jobs, setJobs] = useState<MatchedJob[]>(initialJobs ?? []);
  const [totalCount, setTotalCount] = useState<number | null>(
    () => getCachedMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS)
  );
  const [loading, setLoading] = useState(initialJobs === null && !seedJobs?.length);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState((initialJobs?.length ?? PAGE_SIZE) === PAGE_SIZE);
  const [offset, setOffset] = useState(initialJobs?.length ?? 0);
  const [emptyRefreshCount, setEmptyRefreshCount] = useState(0);

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
          limit: PAGE_SIZE,
          offset: currentOffset,
        };

        const cached = isFirst ? getCachedMatchFeed(filters) : null;
        if (cached) {
          setJobs(applyLocalFilters(cached, { remoteOnly, seniority }));
          setHasMore(cached.length === PAGE_SIZE);
          setOffset(currentOffset + cached.length);
          setLoading(false);
          // Refresh in the background without blocking the sidebar.
          void fetchMatchFeed(filters, { force: true })
            .then((rawData) => {
              const data = applyLocalFilters(rawData, { remoteOnly, seniority });
              setJobs(data);
              setHasMore(rawData.length === PAGE_SIZE);
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
        setHasMore(rawData.length === PAGE_SIZE);
        setOffset(currentOffset + rawData.length);
      } catch (err) {
        const hasBlockingData =
          isFirst &&
          getCachedMatchFeed({
            min_score: minScore,
            limit: PAGE_SIZE,
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
    [minScore, remoteOnly, seniority, offset]
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
    setOffset(0);
    setHasMore(true);
    setEmptyRefreshCount(0);
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minScore, remoteOnly, seniority]);

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
  const sections = groupByTier(displayJobs);
  // Hide headers when the only section is the untiered "More" bucket (e.g. the
  // backend didn't curate this page) — a lone "More matches" header reads oddly.
  const showHeaders =
    sections.length > 1 || (sections.length === 1 && sections[0].key !== MORE_SECTION.key);
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
      {matchSourceBadge === "linkedin" && (
        <p className="text-micro text-ink-500 mb-3 shrink-0">
          <span className="inline-flex items-center rounded-full bg-ink-100 px-2 py-0.5 font-medium text-ink-700">
            Based on LinkedIn
          </span>
          {" "}— upload a CV to sharpen scores.
        </p>
      )}
      {seedJobs?.length ? (
        <p className="text-micro text-ink-500 mb-3 shrink-0">
          <span className="inline-flex items-center rounded-full bg-accent/10 px-2 py-0.5 font-medium text-ink-800">
            From Aarya
          </span>
          {" "}
          {seedTitle
            ? `Including Aarya's jobs for ${seedTitle}.`
            : "Including the roles Aarya just found in chat."}
        </p>
      ) : null}
      {/* ── Filter bar (collapsed behind a toggle) ─────────────────────── */}
      {(() => {
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

        {!loading && !error && visibleCount === 0 && (
          <MatchesEmptyPanel
            onAskAarya={onAskAarya}
            isSearching={emptyRefreshCount < 5}
          />
        )}

        {visibleCount > 0 &&
          sections.map((section) => (
            <div key={section.key} className="space-y-3">
              {showHeaders && (
                <div className="flex items-baseline justify-between pt-1">
                  <h4 className="text-small font-semibold text-ink-900">
                    {section.label}
                    <span className="ml-1.5 text-ink-300 font-normal">
                      {section.jobs.length}
                    </span>
                  </h4>
                  {section.description && (
                    <span className="text-micro text-ink-400">
                      {section.description}
                    </span>
                  )}
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

        {!loading && !error && hasMore && jobs.length > 0 && !seedJobs?.length && (
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
