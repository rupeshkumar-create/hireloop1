"use client";

import { CandidateSidebar } from "@/components/layout/CandidateSidebar";
import type { PanelId } from "@/lib/dashboard/panel-types";

export type TopNavProps = {
  activePanel: PanelId | null;
  onTogglePanel: (id: PanelId) => void;
  onOpenChat?: () => void;
  pendingIntros: boolean;
  showAdminLink: boolean;
  onSignOut: () => void;
  signingOut: boolean;
};

/** Dashboard left rail — delegates to CandidateSidebar in panel-toggle mode. */
export function TopNav({
  activePanel,
  onTogglePanel,
  onOpenChat,
  pendingIntros,
  showAdminLink,
  onSignOut,
  signingOut,
}: TopNavProps) {
  return (
    <CandidateSidebar
      activePanel={activePanel}
      onTogglePanel={onTogglePanel}
      onOpenChat={onOpenChat}
      pendingIntros={pendingIntros}
      showAdminLink={showAdminLink}
      onSignOut={onSignOut}
      signingOut={signingOut}
    />
  );
}
