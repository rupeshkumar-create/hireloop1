/** Client-side flag so the post-onboarding guided chat flow runs once per user. */
export const CAREER_KICKOFF_DONE_KEY = "hireloop_career_kickoff_done_v1";

export function markCareerKickoffDone(userId?: string): void {
  try {
    localStorage.setItem(CAREER_KICKOFF_DONE_KEY, userId ?? "1");
  } catch {
    /* ignore */
  }
}

export function hasCareerKickoffDone(userId?: string): boolean {
  try {
    const stored = localStorage.getItem(CAREER_KICKOFF_DONE_KEY);
    if (!stored) return false;
    if (!userId) return stored === "1" || stored.length > 0;
    return stored === userId || stored === "1";
  } catch {
    return false;
  }
}

export function clearCareerKickoffDone(): void {
  try {
    localStorage.removeItem(CAREER_KICKOFF_DONE_KEY);
  } catch {
    /* ignore */
  }
}
