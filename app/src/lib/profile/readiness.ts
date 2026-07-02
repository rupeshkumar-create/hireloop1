import type { MyProfileData } from "@/lib/api/profile";

type ProfileReadinessCandidate = Pick<
  NonNullable<MyProfileData["candidate"]>,
  "location_city" | "expected_ctc_min" | "expected_ctc_max" | "linkedin_url"
>;

export type ProfileReadinessInput = {
  candidate?: ProfileReadinessCandidate | null;
} | null | undefined;

/** Resume uploaded, or minimal profile (city + expected CTC) — unlocks apply / intro in UI. */
export function canApplyOrIntro(
  profile: ProfileReadinessInput,
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

/** Show dashboard boosters only while apply/intros are locked or resume is missing. */
export function shouldShowProfileBoosters(
  profile: ProfileReadinessInput,
  hasResume: boolean,
): boolean {
  if (!canApplyOrIntro(profile, hasResume)) return true;
  if (hasResume) return false;
  if (profile?.candidate?.linkedin_url?.trim()) return false;
  return true;
}
