/** Client-side grace period after POST /complete-onboarding while profile revalidates. */
export const ONBOARDING_COMPLETE_AT_KEY = "hireloop_onboarding_complete_at";

const DEFAULT_GRACE_MS = 120_000;

export function markClientOnboardingComplete(): void {
  try {
    sessionStorage.setItem(ONBOARDING_COMPLETE_AT_KEY, String(Date.now()));
  } catch {
    /* ignore */
  }
}

export function clearClientOnboardingComplete(): void {
  try {
    sessionStorage.removeItem(ONBOARDING_COMPLETE_AT_KEY);
  } catch {
    /* ignore */
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

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
