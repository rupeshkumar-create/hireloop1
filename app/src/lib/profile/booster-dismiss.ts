const BOOSTERS_DISMISS_PREFIX = "hireloop:profile-boosters-dismissed";

export function profileBoostersDismissKey(userId: string): string {
  return `${BOOSTERS_DISMISS_PREFIX}:${userId}`;
}

export function isProfileBoostersDismissed(userId: string | undefined): boolean {
  if (!userId || typeof window === "undefined") return false;
  return window.localStorage.getItem(profileBoostersDismissKey(userId)) === "1";
}

export function dismissProfileBoosters(userId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(profileBoostersDismissKey(userId), "1");
}
