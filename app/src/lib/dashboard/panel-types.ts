/** Dashboard preview panel identifiers. */
export type PanelId =
  | "home"
  | "inbox"
  | "profile"
  | "jobs"
  | "career_path"
  | "tracker"
  | "coaching"
  | "settings";

/** Matches panel sub-tabs (synced to ?tab= in the URL). */
export type JobsTab = "matches" | "saved";

export const VALID_PANELS: PanelId[] = [
  "home",
  "inbox",
  "profile",
  "jobs",
  "career_path",
  "tracker",
  "coaching",
  "settings",
];

export const VALID_JOBS_TABS: JobsTab[] = ["matches", "saved"];

/** Legacy ?tab=path|tracker → dedicated sidebar panels. */
export const LEGACY_JOBS_TAB_PANEL: Record<string, PanelId> = {
  path: "career_path",
  tracker: "tracker",
};

export const PANEL_TITLE: Record<PanelId, string> = {
  home: "Mission control",
  inbox: "Intros",
  profile: "Profile",
  jobs: "Matches",
  career_path: "Career path",
  tracker: "Job tracker",
  coaching: "Coaching",
  settings: "Settings",
};
