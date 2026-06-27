import type { MyProfileData } from "@/lib/api/profile";

/** Resume uploaded, or minimal profile (city + expected CTC) — unlocks apply / intro in UI. */
export function canApplyOrIntro(
  profile: MyProfileData | null | undefined,
  hasResume: boolean,
): boolean {
  if (hasResume) return true;
  const c = profile?.candidate;
  if (!c) return false;
  const hasCity = Boolean(c.location_city?.trim());
  const hasCtc =
    (c.expected_ctc_min != null && c.expected_ctc_min > 0) ||
    (c.expected_ctc_max != null && c.expected_ctc_max > 0);
  return hasCity && hasCtc;
}

/** Show dashboard boosters until apply is unlocked or profile is fully enriched. */
export function shouldShowProfileBoosters(
  profile: MyProfileData | null | undefined,
  hasResume: boolean,
  hasVoiceSession: boolean,
): boolean {
  if (!canApplyOrIntro(profile, hasResume)) return true;
  return !hasResume || !hasVoiceSession;
}
