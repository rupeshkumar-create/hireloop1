/** Client-side grace period after POST /complete-onboarding while profile revalidates. */
export const ONBOARDING_COMPLETE_AT_KEY = "hireloop_onboarding_complete_at";
export const ONBOARDING_COMPLETE_PERSISTENT_KEY = "hireloop_onboarding_complete_v1";

const DEFAULT_GRACE_MS = 300_000;

export function markClientOnboardingComplete(userId?: string): void {
  try {
    const now = String(Date.now());
    sessionStorage.setItem(ONBOARDING_COMPLETE_AT_KEY, now);
    if (userId) {
      localStorage.setItem(ONBOARDING_COMPLETE_PERSISTENT_KEY, userId);
    }
  } catch {
    /* ignore */
  }
}

export function clearClientOnboardingComplete(): void {
  try {
    sessionStorage.removeItem(ONBOARDING_COMPLETE_AT_KEY);
    localStorage.removeItem(ONBOARDING_COMPLETE_PERSISTENT_KEY);
  } catch {
    /* ignore */
  }
}

export function hasPersistentOnboardingComplete(userId?: string): boolean {
  try {
    const stored = localStorage.getItem(ONBOARDING_COMPLETE_PERSISTENT_KEY);
    if (!stored) return false;
    if (!userId) return stored === "1" || stored.length > 0;
    return stored === userId || stored === "1";
  } catch {
    return false;
  }
}

export function isClientOnboardingCompleteRecent(
  maxAgeMs: number = DEFAULT_GRACE_MS,
): boolean {
  try {
    const raw = sessionStorage.getItem(ONBOARDING_COMPLETE_AT_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    if (!Number.isFinite(ts)) return false;
    return Date.now() - ts < maxAgeMs;
  } catch {
    return false;
  }
}

export function isClientOnboardingTrusted(userId?: string): boolean {
  return (
    isClientOnboardingCompleteRecent() ||
    (userId ? hasPersistentOnboardingComplete(userId) : hasPersistentOnboardingComplete())
  );
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
