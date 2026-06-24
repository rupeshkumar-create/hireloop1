import { fetchCareerIntelligence } from "@/lib/api/career";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeed,
  fetchMatchFeedCount,
} from "@/lib/api/matches";
import { fetchMyProfile, type MyProfileData } from "@/lib/api/profile";

export type ChatWarmupSnapshot = {
  profile: MyProfileData | null;
  matchCount: number | null;
  profileCompleteness: number | null;
};

let cached: ChatWarmupSnapshot | null = null;
let inflight: Promise<ChatWarmupSnapshot> | null = null;

/** Prefetch profile + matches so first "Find jobs" isn't a cold start. */
export async function warmupChatContext(
  options: { force?: boolean } = {}
): Promise<ChatWarmupSnapshot> {
  if (!options.force && cached) return cached;
  if (!options.force && inflight) return inflight;

  inflight = (async () => {
    const snapshot: ChatWarmupSnapshot = {
      profile: null,
      matchCount: null,
      profileCompleteness: null,
    };

    const [profileRes, countRes, intelRes] = await Promise.allSettled([
      fetchMyProfile(),
      fetchMatchFeedCount({ min_score: 0 }),
      fetchCareerIntelligence(),
    ]);

    if (profileRes.status === "fulfilled") snapshot.profile = profileRes.value;
    if (countRes.status === "fulfilled") snapshot.matchCount = countRes.value;
    if (intelRes.status === "fulfilled" && intelRes.value?.data_completeness != null) {
      snapshot.profileCompleteness = Math.min(
        100,
        Math.round(intelRes.value.data_completeness)
      );
    }

    // Prime first page of matches for the Jobs panel too.
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
