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
import { AlertCircle, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeed,
  fetchMatchFeedCount,
  getCachedMatchFeed,
  getCachedMatchFeedCount,
  MATCH_FEED_RELEVANCE_FLOOR,
  type MatchedJob,
  type MatchFeedFilters,
} from "@/lib/api/matches";
import {
  openTailoredDownload,
  pollTailoredResume,
  requestTailoredResume,
} from "@/lib/api/tailored";
import { Button, Card, EmptyState, Select } from "@/components/ui";
import { Stagger, StaggerItem } from "@/components/ui/motion";
import { JobCard } from "./JobCard";

interface MatchFeedProps {
  conversationId?: string;
  onRequestIntro?: (job: MatchedJob) => void;
  savedJobIds?: Set<string>;
  onSavedChange?: (jobId: string, saved: boolean) => void;
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

const PAGE_SIZE = 10;

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
  savedJobIds = new Set(),
  onSavedChange,
  className,
}: MatchFeedProps) {
  const initialJobs = getCachedMatchFeed(DEFAULT_MATCH_FEED_FILTERS);
  const [jobs, setJobs] = useState<MatchedJob[]>(initialJobs ?? []);
  const [totalCount, setTotalCount] = useState<number | null>(
    () => getCachedMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS)
  );
  const [loading, setLoading] = useState(initialJobs === null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(
    (initialJobs?.length ?? PAGE_SIZE) === PAGE_SIZE
  );
  const [offset, setOffset] = useState(initialJobs?.length ?? 0);

  // Filters
  const [minScore, setMinScore] = useState(MATCH_FEED_RELEVANCE_FLOOR);
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [seniority, setSeniority] = useState("");

  // Per-job tailored-resume state
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

  const load = useCallback(
    async (reset = false) => {
      const currentOffset = reset ? 0 : offset;
      const isFirst = reset || currentOffset === 0;

      setError(null);

      try {
        const filters: MatchFeedFilters = {
          min_score: minScore,
          limit: PAGE_SIZE,
          offset: currentOffset,
        };

        const cached = isFirst ? getCachedMatchFeed(filters) : null;
        if (cached) {
          setJobs(applyLocalFilters(cached, { remoteOnly, seniority }));
          setHasMore(cached.length === PAGE_SIZE);
          setOffset(currentOffset + cached.length);
          setLoading(false);
        } else if (isFirst) {
          setLoading(true);
        } else {
          setLoadingMore(true);
        }

        const rawData = await fetchMatchFeed(filters, { force: Boolean(cached) });
        const data = applyLocalFilters(rawData, { remoteOnly, seniority });

        setJobs((prev) => (isFirst ? data : [...prev, ...data]));
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
    load(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minScore, remoteOnly, seniority]);

  const visibleCount = jobs.length;
  const sections = groupByTier(jobs);
  // Hide headers when the only section is the untiered "More" bucket (e.g. the
  // backend didn't curate this page) — a lone "More matches" header reads oddly.
  const showHeaders =
    sections.length > 1 || (sections.length === 1 && sections[0].key !== MORE_SECTION.key);
  const hasLocalFilters = remoteOnly || Boolean(seniority);
  const countLabel = (() => {
    if (loading) return "";
    if (hasLocalFilters) {
      return `${visibleCount} match${visibleCount !== 1 ? "es" : ""} shown`;
    }
    if (totalCount !== null) {
      return `${totalCount} match${totalCount !== 1 ? "es" : ""}`;
    }
    return `${visibleCount} match${visibleCount !== 1 ? "es" : ""}`;
  })();

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* ── Filter bar ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 pb-4 mb-4 border-b border-ink-100 shrink-0">
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

        <span className="ml-auto text-small text-ink-500">
          {countLabel}
        </span>
      </div>

      {/* ── Content ────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-1 pb-6">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => <JobCardSkeleton key={i} />)}

        {!loading && error && (
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

        {!loading && !error && jobs.length === 0 && (
          <EmptyState
            icon={<Search strokeWidth={1.5} />}
            title="No matches yet"
            description="Aarya is finding the best roles for your profile. Check back in a few hours or ask Aarya to search for specific roles."
          />
        )}

        {!loading &&
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
                      onDirectApply={(j) => {
                        if (j.apply_url)
                          window.open(j.apply_url, "_blank", "noopener,noreferrer");
                      }}
                      onTailorResume={handleTailorResume}
                      tailorStatus={tailorByJob[job.job_id] ?? "idle"}
                      isSaved={savedJobIds.has(job.job_id)}
                      onSavedChange={onSavedChange}
                    />
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
          ))}

        {!loading && !error && hasMore && jobs.length > 0 && (
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
