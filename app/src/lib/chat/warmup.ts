import { fetchCareerIntelligence } from "@/lib/api/career";
import { fetchCareerPath } from "@/lib/api/career";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeed,
  fetchMatchFeedCount,
  type MatchedJob,
} from "@/lib/api/matches";
import { fetchMyProfile, type MyProfileData } from "@/lib/api/profile";
import { ensureAaryaSession, prefetchAaryaWarmup, readStoredAaryaSession } from "@/lib/chat/aaryaStream";

export type ChatWarmupSnapshot = {
  profile: MyProfileData | null;
  matchCount: number | null;
  profileCompleteness: number | null;
  prefetchedJobs: MatchedJob[];
  sessionId: string | null;
  careerPathSummary: string | null;
  warmedAt: number;
};

const STALE_MS = 30_000;

let cached: ChatWarmupSnapshot | null = null;
let inflight: Promise<ChatWarmupSnapshot> | null = null;
let idleTimer: ReturnType<typeof setInterval> | null = null;

/** Prefetch profile + matches so first "Find jobs" isn't a cold start. */
export async function warmupChatContext(
  options: { force?: boolean } = {}
): Promise<ChatWarmupSnapshot> {
  const now = Date.now();
  if (
    !options.force &&
    cached &&
    now - cached.warmedAt < STALE_MS
  ) {
    return cached;
  }
  if (!options.force && inflight) return inflight;

  inflight = (async () => {
    const snapshot: ChatWarmupSnapshot = {
      profile: null,
      matchCount: null,
      profileCompleteness: null,
      prefetchedJobs: [],
      sessionId: readStoredAaryaSession(),
      careerPathSummary: null,
      warmedAt: Date.now(),
    };

    const [profileRes, countRes, intelRes, apiWarmup, pathRes] = await Promise.allSettled([
      fetchMyProfile(),
      fetchMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS),
      fetchCareerIntelligence(),
      prefetchAaryaWarmup(),
      fetchCareerPath().catch(() => null),
    ]);

    if (profileRes.status === "fulfilled") snapshot.profile = profileRes.value;
    if (countRes.status === "fulfilled") snapshot.matchCount = countRes.value;
    if (intelRes.status === "fulfilled" && intelRes.value?.data_completeness != null) {
      snapshot.profileCompleteness = Math.min(
        100,
        Math.round(intelRes.value.data_completeness)
      );
    }
    if (apiWarmup.status === "fulfilled") {
      if (apiWarmup.value.profileCompleteness > 0) {
        snapshot.profileCompleteness = apiWarmup.value.profileCompleteness;
      }
      snapshot.prefetchedJobs = apiWarmup.value.prefetchedJobs;
      if (apiWarmup.value.matchCount > 0) {
        snapshot.matchCount = apiWarmup.value.matchCount;
      }
    }
    if (pathRes.status === "fulfilled" && pathRes.value?.steps?.length) {
      const steps = pathRes.value.steps.slice(0, 3);
      snapshot.careerPathSummary = steps.map((s) => s.title).join(" → ");
    }

    try {
      snapshot.sessionId = await ensureAaryaSession(snapshot.sessionId);
    } catch {
      /* session created lazily on first message */
    }

    void fetchMatchFeed(DEFAULT_MATCH_FEED_FILTERS).catch(() => {});

    cached = snapshot;
    inflight = null;
    return snapshot;
  })();

  return inflight;
}

export function getChatWarmupSnapshot(): ChatWarmupSnapshot | null {
  return cached;
}

/** Re-warm stale cache while the user is idle on dashboard/chat. */
export function scheduleIdleWarmupRewarm(intervalMs = 30_000): () => void {
  if (idleTimer) clearInterval(idleTimer);
  idleTimer = setInterval(() => {
    void warmupChatContext({ force: true }).catch(() => undefined);
  }, intervalMs);
  return () => {
    if (idleTimer) {
      clearInterval(idleTimer);
      idleTimer = null;
    }
  };
}
