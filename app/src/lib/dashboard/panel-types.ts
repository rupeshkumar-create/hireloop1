/** Dashboard preview panel identifiers. */
export type PanelId = "home" | "inbox" | "profile" | "jobs" | "coaching";

/** Jobs panel sub-tabs (synced to ?tab= in the URL). */
export type JobsTab = "matches" | "path" | "saved";

export const VALID_PANELS: PanelId[] = [
  "home",
  "inbox",
  "profile",
  "jobs",
  "coaching",
];

export const VALID_JOBS_TABS: JobsTab[] = ["matches", "path", "saved"];

export const PANEL_TITLE: Record<PanelId, string> = {
  home: "Mission control",
  inbox: "Intros",
  profile: "Profile",
  jobs: "Matches",
  coaching: "Coaching",
};
