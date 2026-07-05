import { CANDIDATE_NAV } from "@/lib/candidate-nav";
import type { PanelId } from "@/lib/dashboard/panel-types";

export type RailItem = { id: PanelId; label: string; Icon: React.ElementType };

const NAV_TO_PANEL: Record<string, PanelId> = {
  home: "home",
  matches: "jobs",
  career_path: "career_path",
  tracker: "tracker",
  intros: "inbox",
  profile: "profile",
};

/** Desktop top-nav pills — aligned with CANDIDATE_NAV panel items. */
export const RAIL_ITEMS: RailItem[] = CANDIDATE_NAV.filter((n) => n.id in NAV_TO_PANEL).map(
  (n) => ({
    id: NAV_TO_PANEL[n.id],
    label: n.label,
    Icon: n.Icon,
  }),
);
