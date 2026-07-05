"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal } from "@/components/brand/icons";
import {
  CANDIDATE_MOBILE_MORE_NAV,
  CANDIDATE_MOBILE_PRIMARY_NAV,
  type CandidateNavId,
  type CandidateNavItem,
} from "@/lib/candidate-nav";
import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/utils";

type PanelId = "home" | "inbox" | "profile" | "jobs" | "coaching";

const PANEL_BY_NAV: Partial<Record<CandidateNavId, PanelId>> = {
  home: "home",
  matches: "jobs",
  intros: "inbox",
  profile: "profile",
  coaching: "coaching",
};

type CandidateMobileNavProps = {
  activePanel?: PanelId | null;
  onTogglePanel?: (id: PanelId) => void;
};

const tabClass = (active: boolean) =>
  cn(
    "relative flex flex-1 min-w-0 flex-col items-center justify-center gap-0.5 py-1 transition-colors duration-fast",
    active ? "text-ink-900" : "text-ink-500 hover:text-ink-900",
  );

function NavTab({
  item,
  active,
  onPanelToggle,
}: {
  item: CandidateNavItem;
  active: boolean;
  onPanelToggle?: (id: PanelId) => void;
}) {
  const panelId = PANEL_BY_NAV[item.id];

  if (onPanelToggle && panelId) {
    return (
      <button
        type="button"
        onClick={() => onPanelToggle(panelId)}
        aria-current={active ? "page" : undefined}
        aria-label={item.label}
        className={tabClass(active)}
      >
        {active && (
          <span className="absolute top-1 h-1 w-6 rounded-full bg-accent" aria-hidden />
        )}
        <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
        <span className="text-[10px] font-medium truncate max-w-full px-0.5 leading-tight">
          {item.label}
        </span>
      </button>
    );
  }

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      aria-label={item.label}
      className={tabClass(active)}
    >
      {active && (
        <span className="absolute top-1 h-1 w-6 rounded-full bg-accent" aria-hidden />
      )}
      <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
      <span className="text-[10px] font-medium truncate max-w-full px-0.5 leading-tight">
        {item.label}
      </span>
    </Link>
  );
}

export function CandidateMobileNav({
  activePanel,
  onTogglePanel,
}: CandidateMobileNavProps) {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const dashboardMode = Boolean(onTogglePanel);

  function isItemActive(item: CandidateNavItem) {
    if (dashboardMode && item.id in PANEL_BY_NAV) {
      return activePanel === PANEL_BY_NAV[item.id as keyof typeof PANEL_BY_NAV];
    }
    const base = item.href.split("?")[0];
    if (pathname === base) return true;
    return item.match?.some((m) => pathname?.startsWith(m)) ?? false;
  }

  const moreActive = CANDIDATE_MOBILE_MORE_NAV.some(isItemActive);

  return (
    <>
      <nav
        className="fixed inset-x-0 bottom-0 z-30 flex h-16 items-stretch border-t border-ink-100 bg-paper-1 md:hidden pb-[env(safe-area-inset-bottom)] px-1"
        aria-label="Primary navigation"
      >
        {CANDIDATE_MOBILE_PRIMARY_NAV.map((item) => (
          <NavTab
            key={item.id}
            item={item}
            active={isItemActive(item)}
            onPanelToggle={dashboardMode ? onTogglePanel : undefined}
          />
        ))}

        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          aria-label="More navigation"
          aria-expanded={moreOpen}
          className={tabClass(moreActive)}
        >
          {moreActive && (
            <span className="absolute top-1 h-1 w-6 rounded-full bg-accent" aria-hidden />
          )}
          <MoreHorizontal className="h-5 w-5 shrink-0" strokeWidth={1.5} />
          <span className="text-[10px] font-medium">More</span>
        </button>
      </nav>

      <Modal open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <ul className="space-y-1 -mx-1">
          {CANDIDATE_MOBILE_MORE_NAV.map((item) => {
            const panelId = PANEL_BY_NAV[item.id];
            const active = isItemActive(item);

            if (dashboardMode && panelId && onTogglePanel) {
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setMoreOpen(false);
                      onTogglePanel(panelId);
                    }}
                    className={cn(
                      "w-full flex items-center gap-3 rounded-lg px-3 py-3 text-left transition-colors",
                      active ? "bg-ink-50 text-ink-900" : "hover:bg-ink-50 text-ink-700",
                    )}
                  >
                    <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
                    <span className="text-body font-medium">{item.label}</span>
                  </button>
                </li>
              );
            }

            return (
              <li key={item.id}>
                <Link
                  href={item.href}
                  onClick={() => setMoreOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-3 transition-colors",
                    active ? "bg-ink-50 text-ink-900" : "hover:bg-ink-50 text-ink-700",
                  )}
                >
                  <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
                  <span className="text-body font-medium">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </Modal>
    </>
  );
}
