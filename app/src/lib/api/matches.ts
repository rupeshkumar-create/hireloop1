/**
 * Match feed API client — wraps GET /api/v1/matches and related endpoints.
 * All calls go through the FastAPI backend (never direct Supabase from frontend).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { recordJobApplication } from "@/lib/api/job-applications";
import { loadMatchHistoryWithRecovery } from "@/lib/api/match-history-recovery";

// ── Types ─────────────────────────────────────────────────────────────────────

export type MatchedJob = {
  job_id: string;
  title: string;
  company_name: string | null;
  company_logo_url?: string | null;
  location_city: string | null;
  location_state: string | null;
  is_remote: boolean;
  seniority: string | null;
  employment_type: string | null;
  ctc_min: number | null;
  ctc_max: number | null;
  salary_currency?: string | null;
  skills_required: string[];
  apply_url: string | null;
  // Full posting detail (single-match endpoint)
  description?: string | null;
  requirements?: string | null;
  posted_at?: string | null;
  // Skill detail — which required skills the candidate has vs is missing.
  skills_matched?: string[];
  skills_gap?: string[];
  // Scores
  overall_score: number;       // 0–1
  skills_score: number | null;
  experience_score: number | null;
  location_score: number | null;
  ctc_score: number | null;
  culture_score?: number | null;
  career_alignment_score?: number | null;
  fit_recommendation?: "apply" | "stretch" | "skip" | null;
  salary_benchmark?: {
    market_median?: number;
    vs_market?: string;
    vs_market_label?: string;
    unit?: string;
    currency?: string;
  } | null;
  triage_notes?: string | null;
  explanation: string | null;
  computed_at: string;
  // Retention: jobs new since the candidate's last dashboard visit.
  is_new_since_visit?: boolean;
  // Retention: job is new to this candidate (not previously surfaced).
  is_new_for_you?: boolean;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  // Presentation layer — confidence badge from the API ranking layer.
  tier?: string | null;
  tier_label?: string | null;
  // Action-state — what's already been done for this role (kit prepared, intro
  // requested/sent…). null when the candidate hasn't acted on it yet.
  action_state?: "kit_ready" | "intro" | "applied" | null;
  action_label?: string | null;
};

export type MatchFeedFilters = {
  min_score?: number;   // 0–1
  limit?: number;
  offset?: number;
  only_new?: boolean;
};

export type FindNewJobsResult = {
  jobs: MatchedJob[];
  refreshing: boolean;
  excluded_count: number;
  message: string | null;
};

export type JobAction = "request_intro" | "direct_apply" | "save";

type FetchMatchFeedOptions = {
  force?: boolean;
};

// ── In-memory match feed cache ───────────────────────────────────────────────
//
// MatchFeed owns this cache after the user explicitly starts job search. Keeping
// it here prevents duplicate requests while filters or tabs re-render.

const _matchFeedCache = new Map<string, MatchedJob[]>();
const _matchFeedInFlight = new Map<string, Promise<MatchedJob[]>>();
const _matchFeedCountCache = new Map<string, number>();
const _matchFeedCountInFlight = new Map<string, Promise<number>>();

/** Browser-only event to notify already-mounted MatchFeed components. */
export const MATCH_FEED_INVALIDATE_EVENT = "hireloop:match-feed-invalidated";

function matchFeedCacheKey(filters: MatchFeedFilters = {}): string {
  return JSON.stringify({
    min_score: filters.min_score ?? null,
    limit: filters.limit ?? null,
    offset: filters.offset ?? null,
    only_new: filters.only_new ?? false,
  });
}

function matchFeedCountCacheKey(filters: Pick<MatchFeedFilters, "min_score"> = {}): string {
  return JSON.stringify({ min_score: filters.min_score ?? MATCH_FEED_RELEVANCE_FLOOR });
}

export function getCachedMatchFeed(
  filters: MatchFeedFilters = {}
): MatchedJob[] | null {
  return _matchFeedCache.get(matchFeedCacheKey(filters)) ?? null;
}

export function getCachedMatchFeedCount(
  filters: Pick<MatchFeedFilters, "min_score"> = {}
): number | null {
  return _matchFeedCountCache.get(matchFeedCountCacheKey(filters)) ?? null;
}

export function invalidateMatchFeedCache(): void {
  _matchFeedCache.clear();
  _matchFeedInFlight.clear();
  _matchFeedCountCache.clear();
  _matchFeedCountInFlight.clear();

  // If the sidebar is already mounted, it needs an explicit signal to re-fetch
  // (cache invalidation alone doesn't affect React state).
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(MATCH_FEED_INVALIDATE_EVENT));
  }
}

/** Default filters shared by Home stat card and Jobs → Matches tab. */
export const DEFAULT_MATCH_FEED_FILTERS: MatchFeedFilters = {
  min_score: 0.38,
  limit: 50,
  offset: 0,
};

/** Initial page size for the Matches sidebar feed. */
export const MATCH_FEED_PAGE_SIZE = 50;

/** Quality-first relevance floor (matches API DEFAULT_FEED_MIN_SCORE). */
export const MATCH_FEED_RELEVANCE_FLOOR = 0.38;

const MATCH_FEED_FETCH_TIMEOUT_MS = 45_000;

// ── API calls ─────────────────────────────────────────────────────────────────

export async function fetchMatchTriage(limit = 10): Promise<MatchedJob[]> {
  const res = await apiAuthFetch(`/api/v1/matches/triage?limit=${limit}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Match triage failed: ${res.status}`);
  }
  return res.json() as Promise<MatchedJob[]>;
}

export async function fetchMatchFeed(
  filters: MatchFeedFilters = {},
  options: FetchMatchFeedOptions = {}
): Promise<MatchedJob[]> {
  const cacheKey = matchFeedCacheKey(filters);
  if (!options.force) {
    const cached = _matchFeedCache.get(cacheKey);
    if (cached) return cached;

    const inFlight = _matchFeedInFlight.get(cacheKey);
    if (inFlight) return inFlight;
  }

  const params = new URLSearchParams();
  if (filters.min_score !== undefined)
    params.set("min_score", String(filters.min_score));
  if (filters.limit !== undefined)
    params.set("limit", String(filters.limit));
  if (filters.offset !== undefined)
    params.set("offset", String(filters.offset));
  if (filters.only_new) params.set("only_new", "true");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), MATCH_FEED_FETCH_TIMEOUT_MS);

  const req = apiAuthFetch(`/api/v1/matches?${params.toString()}`, {
    cache: "no-store",
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `Match feed failed: ${res.status}`);
      }

      const data = (await res.json()) as MatchedJob[];
      _matchFeedCache.set(cacheKey, data);
      return data;
    })
    .catch((err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new Error("Match feed timed out. Pull to refresh or try again.");
      }
      throw err;
    })
    .finally(() => {
      clearTimeout(timeoutId);
      if (_matchFeedInFlight.get(cacheKey) === req) {
        _matchFeedInFlight.delete(cacheKey);
      }
    });

  _matchFeedInFlight.set(cacheKey, req);
  return req;
}

export async function fetchMatchFeedCount(
  filters: Pick<MatchFeedFilters, "min_score"> = {},
  options: FetchMatchFeedOptions = {}
): Promise<number> {
  const cacheKey = matchFeedCountCacheKey(filters);
  if (!options.force) {
    const cached = _matchFeedCountCache.get(cacheKey);
    if (cached !== undefined) return cached;

    const inFlight = _matchFeedCountInFlight.get(cacheKey);
    if (inFlight) return inFlight;
  }

  const params = new URLSearchParams();
  if (filters.min_score !== undefined) {
    params.set("min_score", String(filters.min_score));
  }

  const req = apiAuthFetch(`/api/v1/matches/count?${params.toString()}`, {
    cache: "no-store",
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `Match count failed: ${res.status}`);
      }
      const data = (await res.json()) as { total: number };
      const total = Number(data.total) || 0;
      _matchFeedCountCache.set(cacheKey, total);
      return total;
    })
    .finally(() => {
      if (_matchFeedCountInFlight.get(cacheKey) === req) {
        _matchFeedCountInFlight.delete(cacheKey);
      }
    });

  _matchFeedCountInFlight.set(cacheKey, req);
  return req;
}

export async function fetchMatchHistory(
  filters: Pick<MatchFeedFilters, "min_score" | "limit" | "offset"> = {},
): Promise<MatchedJob[]> {
  const params = new URLSearchParams();
  if (filters.min_score !== undefined) {
    params.set("min_score", String(filters.min_score));
  }
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.offset !== undefined) params.set("offset", String(filters.offset));

  const result = await loadMatchHistoryWithRecovery<MatchedJob>(async () => {
    const res = await apiAuthFetch(`/api/v1/matches/history?${params.toString()}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => ({}))) as { detail?: string };
      return {
        ok: false,
        status: res.status,
        jobs: [],
        detail: err.detail ?? `Match history failed: ${res.status}`,
      };
    }
    return {
      ok: true,
      status: res.status,
      jobs: (await res.json()) as MatchedJob[],
    };
  });
  if (!result.ok) {
    throw new Error(result.detail ?? `Match history failed: ${result.status}`);
  }
  return result.jobs;
}

export async function findNewMatches(): Promise<FindNewJobsResult> {
  const res = await apiAuthFetch("/api/v1/matches/find-new", {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Find new jobs failed: ${res.status}`);
  }
  return res.json() as Promise<FindNewJobsResult>;
}

export async function fetchSingleMatch(jobId: string): Promise<MatchedJob> {
  const res = await apiAuthFetch(`/api/v1/matches/${jobId}`, {
    cache: "no-store",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Match fetch failed: ${res.status}`);
  }

  return res.json();
}

/**
 * Record a direct application and open the employer apply page.
 */
export async function recordDirectApply(
  _conversationId: string,
  jobId: string,
  applyUrl: string
): Promise<void> {
  window.open(applyUrl, "_blank", "noopener,noreferrer");
  await recordJobApplication(jobId).catch(() => undefined);
}
