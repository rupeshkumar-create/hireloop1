import { CANDIDATE_NAV } from "@/lib/candidate-nav";
import type { PanelId } from "@/lib/dashboard/panel-types";

export type RailItem = {
  id: string;
  label: string;
  Icon: React.ElementType;
  /** null = chat (no side panel) */
  panel: PanelId | null;
};

const NAV_TO_PANEL: Record<string, PanelId | null> = {
  chat: null,
  matches: "jobs",
  intros: "inbox",
  profile: "profile",
};

/** Desktop left rail — Chat · Matches · Intros · Profile */
export const RAIL_ITEMS: RailItem[] = CANDIDATE_NAV.map((n) => ({
  id: n.id,
  label: n.label,
  Icon: n.Icon,
  panel: NAV_TO_PANEL[n.id] ?? null,
}));
