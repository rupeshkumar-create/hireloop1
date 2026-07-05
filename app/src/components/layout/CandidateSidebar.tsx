"use client";

/**
 * CandidateSidebar — single left rail for dashboard + standalone pages.
 * Dashboard: panel toggles. Other routes: links back to dashboard panels.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { HelpCircle, LogOut, Settings, Shield } from "@/components/brand/icons";
import { RoleSwitchButton } from "@/components/layout/RoleSwitchButton";
import { RAIL_ITEMS } from "@/lib/dashboard/rail-items";
import type { PanelId } from "@/lib/dashboard/panel-types";
import { NOTIFICATION_CATEGORIES } from "@/lib/notification-categories";
import { NotificationDrawer } from "@/components/ux";
import { HireLogoMark } from "@/components/brand/HireLogo";
import { cn } from "@/lib/utils";

const PANEL_HREF: Record<PanelId, string> = {
  home: "/dashboard?panel=home",
  inbox: "/dashboard?panel=inbox",
  profile: "/dashboard?panel=profile",
  jobs: "/dashboard?panel=jobs",
  coaching: "/dashboard?panel=coaching",
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
  if (pathname.startsWith("/mock-interview")) return "coaching";
  return null;
}

export type CandidateSidebarProps = {
  activePanel?: PanelId | null;
  onTogglePanel?: (id: PanelId) => void;
  pendingIntros?: boolean;
  showAdminLink?: boolean;
  onSignOut?: () => void;
  signingOut?: boolean;
};

export function CandidateSidebar({
  activePanel = null,
  onTogglePanel,
  pendingIntros = false,
  showAdminLink = false,
  onSignOut,
  signingOut = false,
}: CandidateSidebarProps) {
  const pathname = usePathname();
  const linkMode = !onTogglePanel;
  const resolvedPanel = linkMode ? activePanelFromPath(pathname) : activePanel;
  const settingsActive = pathname === "/settings";

  const utilityClass = (active: boolean) =>
    cn(
      "flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-fast",
      active
        ? "bg-ink-900 text-paper-0"
        : "text-ink-500 hover:bg-ink-50 hover:text-ink-900",
    );

  const railClass = (active: boolean) =>
    cn(
      "relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-fast",
      active ? "bg-ink-900 text-paper-0" : "text-ink-500 hover:bg-ink-50 hover:text-ink-900",
    );

  return (
    <aside className="hidden md:flex w-16 shrink-0 flex-col items-center border-r border-ink-100 bg-paper-1 py-3">
      <Link href="/dashboard" aria-label="Hireloop home" title="Hireloop" className="mb-4">
        <HireLogoMark size={36} />
      </Link>

      <nav className="flex flex-1 flex-col items-center gap-1">
        {RAIL_ITEMS.map((item) => {
          const isActive = resolvedPanel === item.id;
          const showDot = item.id === "inbox" && pendingIntros;

          if (linkMode) {
            return (
              <Link
                key={item.id}
                href={PANEL_HREF[item.id]}
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
              onClick={() => onTogglePanel?.(item.id)}
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

      <div className="mt-2 flex flex-col items-center gap-1">
        <RoleSwitchButton to="recruiter" target="/recruiter/inbox" variant="icon" />
        <NotificationDrawer
          pendingIntros={pendingIntros}
          categories={NOTIFICATION_CATEGORIES}
        />
        {showAdminLink && (
          <Link href="/admin" title="Admin" aria-label="Admin" className={utilityClass(false)}>
            <Shield className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </Link>
        )}
        <Link
          href="/settings"
          title="Settings"
          aria-label="Settings"
          aria-current={settingsActive ? "page" : undefined}
          className={utilityClass(settingsActive)}
        >
          <Settings className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </Link>
        <a
          href="https://hireloop.in/help"
          target="_blank"
          rel="noopener noreferrer"
          title="Help"
          aria-label="Help"
          className={utilityClass(false)}
        >
          <HelpCircle className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </a>
        {onSignOut && (
          <button
            type="button"
            onClick={onSignOut}
            disabled={signingOut}
            title="Sign out"
            aria-label="Sign out"
            className={cn(utilityClass(false), "disabled:opacity-50")}
          >
            <LogOut className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </button>
        )}
      </div>
    </aside>
  );
}
