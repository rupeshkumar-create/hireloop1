/** Client-side flag so the post-onboarding guided chat flow runs once per user. */
export const CAREER_KICKOFF_DONE_KEY = "hireloop_career_kickoff_done_v1";
export const CAREER_KICKOFF_PROGRESS_KEY = "hireloop_career_kickoff_progress_v1";

export type KickoffProgressStep = "analysis" | "paths" | "review";

export type KickoffProgress = {
  step: KickoffProgressStep;
  selected: string[];
  options: Array<{ title: string; rationale: string | null; custom?: boolean }>;
  userId?: string;
};

export function markCareerKickoffDone(userId?: string): void {
  if (!userId) return;
  try {
    localStorage.setItem(CAREER_KICKOFF_DONE_KEY, userId);
    clearCareerKickoffProgress();
  } catch {
    /* ignore */
  }
}

export function hasCareerKickoffDone(userId?: string): boolean {
  if (!userId) return false;
  try {
    const stored = localStorage.getItem(CAREER_KICKOFF_DONE_KEY);
    if (!stored) return false;
    return stored === userId;
  } catch {
    return false;
  }
}

export function clearCareerKickoffDone(userId?: string): void {
  try {
    if (userId) {
      const stored = localStorage.getItem(CAREER_KICKOFF_DONE_KEY);
      if (stored && stored !== userId) return;
    }
    localStorage.removeItem(CAREER_KICKOFF_DONE_KEY);
  } catch {
    /* ignore */
  }
}

export function saveCareerKickoffProgress(
  progress: KickoffProgress,
  userId?: string,
): void {
  if (!userId) return;
  try {
    sessionStorage.setItem(
      CAREER_KICKOFF_PROGRESS_KEY,
      JSON.stringify({ ...progress, userId }),
    );
  } catch {
    /* ignore */
  }
}

export function readCareerKickoffProgress(userId?: string): KickoffProgress | null {
  if (!userId) return null;
  try {
    const raw = sessionStorage.getItem(CAREER_KICKOFF_PROGRESS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as KickoffProgress;
    if (!parsed?.step || !Array.isArray(parsed.selected)) return null;
    if (parsed.userId !== userId) {
      return null;
    }
    return {
      step: parsed.step,
      selected: parsed.selected,
      options: Array.isArray(parsed.options) ? parsed.options : [],
      userId: parsed.userId,
    };
  } catch {
    return null;
  }
}

export function hasCareerKickoffInProgress(userId?: string): boolean {
  return readCareerKickoffProgress(userId) != null;
}

export function clearCareerKickoffProgress(): void {
  try {
    sessionStorage.removeItem(CAREER_KICKOFF_PROGRESS_KEY);
  } catch {
    /* ignore */
  }
}
