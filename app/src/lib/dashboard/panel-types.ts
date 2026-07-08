/** Dashboard preview panel identifiers (minimal shell). */
export type PanelId = "inbox" | "profile" | "jobs" | "settings";

/** Matches panel sub-tabs (synced to ?tab= in the URL). */
export type JobsTab = "matches" | "saved" | "applied";

export type ProfileTabId = "overview" | "experience" | "intelligence" | "preferences";

export const VALID_PANELS: PanelId[] = ["inbox", "profile", "jobs", "settings"];

export const VALID_JOBS_TABS: JobsTab[] = ["matches", "saved", "applied"];

export const VALID_PROFILE_TABS: ProfileTabId[] = [
  "overview",
  "experience",
  "intelligence",
  "preferences",
];

/** Legacy ?panel= values → panel + optional sub-tabs. */
export type LegacyPanelRedirect = {
  panel: PanelId | null;
  jobsTab?: JobsTab;
  profileTab?: ProfileTabId;
};

export const LEGACY_PANEL_REDIRECT: Record<string, LegacyPanelRedirect> = {
  home: { panel: null },
  career_path: { panel: "profile", profileTab: "intelligence" },
  coaching: { panel: null },
  tracker: { panel: "jobs", jobsTab: "applied" },
};

/** Legacy ?tab= under Matches → panel + sub-tab. */
export const LEGACY_JOBS_TAB_REDIRECT: Record<string, LegacyPanelRedirect> = {
  path: { panel: "profile", profileTab: "intelligence" },
  tracker: { panel: "jobs", jobsTab: "applied" },
};

export const PANEL_TITLE: Record<PanelId, string> = {
  inbox: "Intros",
  profile: "Profile",
  jobs: "Matches",
  settings: "Settings",
};
