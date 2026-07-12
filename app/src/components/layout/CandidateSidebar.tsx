"use client";

/**
 * CandidateSidebar — Chat · Matches · Intros · Profile, plus a single More menu.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { HelpCircle, LogOut, MoreHorizontal, Settings, Shield } from "@/components/brand/icons";
import { RoleSwitchButton } from "@/components/layout/RoleSwitchButton";
import { RAIL_ITEMS } from "@/lib/dashboard/rail-items";
import type { PanelId } from "@/lib/dashboard/panel-types";
import { NotificationDrawer } from "@/components/ux";
import { HireschemaLogoMark } from "@/components/brand/HireschemaLogo";
import { cn } from "@/lib/utils";

const PANEL_HREF: Record<PanelId, string> = {
  inbox: "/dashboard?panel=inbox",
  profile: "/dashboard?panel=profile",
  jobs: "/dashboard?panel=jobs",
  settings: "/dashboard?panel=settings",
};

function activePanelFromPath(pathname: string | null): PanelId | null {
  if (!pathname) return null;
  if (pathname.startsWith("/intros")) return "inbox";
  if (
    pathname.startsWith("/jobs") ||
    pathname.startsWith("/matches") ||
    pathname === "/resumes"
  ) {
    return "jobs";
  }
  return null;
}

export type CandidateSidebarProps = {
  activePanel?: PanelId | null;
  onTogglePanel?: (id: PanelId) => void;
  onOpenChat?: () => void;
  pendingIntros?: boolean;
  showAdminLink?: boolean;
  onSignOut?: () => void;
  signingOut?: boolean;
};

export function CandidateSidebar({
  activePanel = null,
  onTogglePanel,
  onOpenChat,
  pendingIntros = false,
  showAdminLink = false,
  onSignOut,
  signingOut = false,
}: CandidateSidebarProps) {
  const pathname = usePathname();
  const linkMode = !onTogglePanel;
  const resolvedPanel = linkMode ? activePanelFromPath(pathname) : activePanel;
  const chatActive = !resolvedPanel;
  const settingsActive = linkMode
    ? pathname === "/settings" || pathname?.includes("panel=settings")
    : activePanel === "settings";
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  const railClass = (active: boolean) =>
    cn(
      "relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-fast",
      active ? "bg-ink-900 text-paper-0" : "text-ink-500 hover:bg-ink-50 hover:text-ink-900",
    );

  return (
    <aside className="hidden md:flex w-16 shrink-0 flex-col items-center border-r border-ink-100 bg-paper-1 py-3">
      <Link href="/dashboard" aria-label="Hireschema home" title="Hireschema" className="mb-4">
        <HireschemaLogoMark size={36} />
      </Link>

      <nav className="flex flex-1 flex-col items-center gap-1">
        {RAIL_ITEMS.map((item) => {
          const isChat = item.panel === null;
          const isActive = isChat ? chatActive : resolvedPanel === item.panel;
          const showDot = item.panel === "inbox" && pendingIntros;

          if (linkMode) {
            const href = isChat ? "/dashboard" : PANEL_HREF[item.panel as PanelId];
            return (
              <Link
                key={item.id}
                href={href}
                title={item.label}
                aria-label={item.label}
                aria-current={isActive ? "page" : undefined}
                className={railClass(isActive)}
              >
                <item.Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
                {showDot && (
                  <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-accent" />
                )}
              </Link>
            );
          }

          return (
            <button
              key={item.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => {
                if (isChat) onOpenChat?.();
                else if (item.panel) onTogglePanel?.(item.panel);
              }}
              title={item.label}
              aria-label={item.label}
              className={railClass(isActive)}
            >
              <item.Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
              {showDot && (
                <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-accent" />
              )}
            </button>
          );
        })}
      </nav>

      <div className="relative mt-2" ref={menuRef}>
        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="More"
          aria-expanded={menuOpen}
          title="More"
          className={railClass(menuOpen || settingsActive)}
        >
          <MoreHorizontal className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </button>

        {menuOpen && (
          <div className="absolute bottom-0 left-full z-30 ml-2 w-52 rounded-lg border border-ink-100 bg-paper-1 py-1 shadow-2 animate-fade-in">
            <div className="px-2 py-1.5">
              <RoleSwitchButton to="recruiter" target="/recruiter/inbox" variant="row" />
            </div>
            <div className="border-t border-ink-100 px-1 py-1">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setNotifOpen(true);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-small text-ink-800 hover:bg-ink-50"
              >
                Notifications
                {pendingIntros && (
                  <span className="ml-auto h-2 w-2 rounded-full bg-accent" />
                )}
              </button>
            </div>
            {showAdminLink && (
              <Link
                href="/admin"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-small text-ink-800 hover:bg-ink-50"
              >
                <Shield className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                Admin
              </Link>
            )}
            {linkMode ? (
              <Link
                href="/dashboard?panel=settings"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-small text-ink-800 hover:bg-ink-50"
              >
                <Settings className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                Settings
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onTogglePanel?.("settings");
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-small text-ink-800 hover:bg-ink-50"
              >
                <Settings className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                Settings
              </button>
            )}
            <a
              href="https://hireschema.com/help"
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-small text-ink-800 hover:bg-ink-50"
            >
              <HelpCircle className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
              Help
            </a>
            {onSignOut && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  onSignOut();
                }}
                disabled={signingOut}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-small text-ink-800 hover:bg-ink-50 disabled:opacity-50"
              >
                <LogOut className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                Sign out
              </button>
            )}
          </div>
        )}
      </div>

      <NotificationDrawer
        pendingIntros={pendingIntros}
        open={notifOpen}
        onOpenChange={setNotifOpen}
        hideTrigger
      />
    </aside>
  );
}
