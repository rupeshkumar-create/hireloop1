"use client";

import { useQuery } from "@tanstack/react-query";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeedCount,
} from "@/lib/api/matches";
import { fetchMyProfile } from "@/lib/api/profile";

export function useProfileQuery() {
  return useQuery({
    queryKey: ["profile", "me"],
    queryFn: fetchMyProfile,
    staleTime: 60_000,
  });
}

export function useMatchCountQuery() {
  return useQuery({
    queryKey: ["matches", "count", DEFAULT_MATCH_FEED_FILTERS],
    queryFn: () => fetchMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS),
    staleTime: 60_000,
  });
}
