/**
 * Match feed API client — wraps GET /api/v1/matches and related endpoints.
 * All calls go through the FastAPI backend (never direct Supabase from frontend).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";

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
  explanation: string | null;
  computed_at: string;
  // Presentation layer — confidence badge from the API ranking layer.
  tier?: string | null;
  tier_label?: string | null;
  // Action-state — what's already been done for this role (kit prepared, intro
  // requested/sent…). null when the candidate hasn't acted on it yet.
  action_state?: "kit_ready" | "intro" | null;
  action_label?: string | null;
};

export type MatchFeedFilters = {
  min_score?: number;   // 0–1
  limit?: number;
  offset?: number;
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

function matchFeedCacheKey(filters: MatchFeedFilters = {}): string {
  return JSON.stringify({
    min_score: filters.min_score ?? null,
    limit: filters.limit ?? null,
    offset: filters.offset ?? null,
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

// ── API calls ─────────────────────────────────────────────────────────────────

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

  const req = apiAuthFetch(`/api/v1/matches?${params.toString()}`, {
    cache: "no-store",
  }).then(async (res) => {
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? `Match feed failed: ${res.status}`);
    }

    const data = (await res.json()) as MatchedJob[];
    _matchFeedCache.set(cacheKey, data);
    return data;
  }).finally(() => {
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
 * Record a direct application through the Aarya chat API.
 * Opens the apply URL in a new tab AND logs the application in the DB.
 */
export async function recordDirectApply(
  conversationId: string,
  jobId: string,
  applyUrl: string
): Promise<void> {
  // Open the job's native apply page immediately (don't block on API call)
  window.open(applyUrl, "_blank", "noopener,noreferrer");

  // Fire-and-forget — log the application
  await apiAuthFetch(`/api/v1/chat/sessions/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: `direct_apply:${jobId}`,
      content_type: "text",
    }),
  }).catch(() => {/* silent — the tab already opened */});
}
