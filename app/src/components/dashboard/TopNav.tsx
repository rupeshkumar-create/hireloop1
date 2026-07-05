"use client";

import Link from "next/link";
import { HelpCircle, LogOut, Settings, Shield } from "@/components/brand/icons";
import { RAIL_ITEMS } from "@/lib/dashboard/rail-items";
import type { PanelId } from "@/lib/dashboard/panel-types";
import { NOTIFICATION_CATEGORIES } from "@/lib/notification-categories";
import { NotificationDrawer } from "@/components/ux";
import { HireLogoMark } from "@/components/brand/HireLogo";
import { cn } from "@/lib/utils";

export type TopNavProps = {
  activePanel: PanelId | null;
  onTogglePanel: (id: PanelId) => void;
  pendingIntros: boolean;
  showAdminLink: boolean;
  onSignOut: () => void;
  signingOut: boolean;
};

/**
 * Left icon rail — the single navigation chrome shared with AppShell (DESIGN.md
 * §6: one shell). Nav items toggle the dashboard's preview panels; utility
 * actions (notifications, admin, settings, help, sign out) sit at the bottom.
 * Hidden on mobile, where CandidateMobileNav takes over.
 */
export function TopNav({
  activePanel,
  onTogglePanel,
  pendingIntros,
  showAdminLink,
  onSignOut,
  signingOut,
}: TopNavProps) {
  const utilityClass =
    "flex h-10 w-10 items-center justify-center rounded-lg text-ink-500 " +
    "hover:bg-ink-50 hover:text-ink-900 transition-colors duration-fast";

  return (
    <aside className="hidden md:flex w-16 shrink-0 flex-col items-center border-r border-ink-100 bg-paper-1 py-3">
      <Link
        href="/dashboard"
        aria-label="Hireloop home"
        title="Hireloop"
        className="mb-4"
      >
        <HireLogoMark size={36} />
      </Link>

      <nav className="flex flex-1 flex-col items-center gap-1">
        {RAIL_ITEMS.map((item) => {
          const isActive = activePanel === item.id;
          const showDot = item.id === "inbox" && pendingIntros;
          return (
            <button
              key={item.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => onTogglePanel(item.id)}
              title={item.label}
              aria-label={item.label}
              className={cn(
                "relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-fast",
                isActive
                  ? "bg-ink-900 text-paper-0"
                  : "text-ink-500 hover:bg-ink-50 hover:text-ink-900",
              )}
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
        <NotificationDrawer
          pendingIntros={pendingIntros}
          categories={NOTIFICATION_CATEGORIES}
        />
        {showAdminLink && (
          <Link href="/admin" title="Admin" aria-label="Admin" className={utilityClass}>
            <Shield className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </Link>
        )}
        <Link href="/settings" title="Settings" aria-label="Settings" className={utilityClass}>
          <Settings className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </Link>
        <a
          href="https://hireloop.in/help"
          target="_blank"
          rel="noopener noreferrer"
          title="Help"
          aria-label="Help"
          className={utilityClass}
        >
          <HelpCircle className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </a>
        <button
          type="button"
          onClick={onSignOut}
          disabled={signingOut}
          title="Sign out"
          aria-label="Sign out"
          className={cn(utilityClass, "disabled:opacity-50")}
        >
          <LogOut className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </button>
      </div>
    </aside>
  );
}
