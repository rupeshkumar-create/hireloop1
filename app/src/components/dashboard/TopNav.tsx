"use client";

import Link from "next/link";
import { HelpCircle, LogOut, Shield } from "lucide-react";
import { RAIL_ITEMS } from "@/lib/dashboard/rail-items";
import type { PanelId } from "@/lib/dashboard/panel-types";
import { NOTIFICATION_CATEGORIES } from "@/lib/notification-categories";
import { NotificationDrawer } from "@/components/ux";
import { cn } from "@/lib/utils";

export type TopNavProps = {
  activePanel: PanelId | null;
  onTogglePanel: (id: PanelId) => void;
  pendingIntros: boolean;
  showAdminLink: boolean;
  onSignOut: () => void;
  signingOut: boolean;
};

export function TopNav({
  activePanel,
  onTogglePanel,
  pendingIntros,
  showAdminLink,
  onSignOut,
  signingOut,
}: TopNavProps) {
  return (
    <header className="shrink-0 h-16 flex items-center gap-3 px-4 md:px-5 border-b border-ink-100 bg-paper-0">
      <Link
        href="/dashboard"
        className="flex items-center gap-2 shrink-0"
        aria-label="Hireloop home"
        title="Hireloop"
      >
        <div className="w-9 h-9 rounded-xl bg-ink-900 flex items-center justify-center">
          <span className="text-paper-0 text-small font-semibold">H</span>
        </div>
        <span className="hidden lg:block text-small font-semibold text-ink-900">Hireloop</span>
      </Link>

      <nav className="flex items-center gap-1 flex-1 min-w-0 overflow-x-auto">
        {RAIL_ITEMS.map((item) => {
          const isActive = activePanel === item.id;
          const showDot = item.id === "inbox" && pendingIntros;

          return (
            <button
              key={item.id}
              aria-pressed={isActive}
              onClick={() => onTogglePanel(item.id)}
              className={cn(
                "relative inline-flex items-center gap-2 rounded-full px-3.5 py-2 shrink-0",
                "text-small font-medium transition-colors duration-fast",
                isActive
                  ? "bg-ink-900 text-paper-0"
                  : "text-ink-500 hover:text-ink-900 hover:bg-ink-50",
              )}
            >
              <item.Icon className="h-[17px] w-[17px]" strokeWidth={1.5} />
              <span>{item.label}</span>
              {showDot && <span className="w-[7px] h-[7px] rounded-full bg-accent" />}
            </button>
          );
        })}
      </nav>

      <div className="flex items-center gap-1 shrink-0">
        <NotificationDrawer
          pendingIntros={pendingIntros}
          categories={NOTIFICATION_CATEGORIES}
        />
        {showAdminLink && (
          <Link
            href="/admin"
            title="Admin"
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast"
          >
            <Shield className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </Link>
        )}
        <a
          href="https://hireloop.in/help"
          target="_blank"
          rel="noopener noreferrer"
          title="Help"
          className="w-9 h-9 rounded-full flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast"
        >
          <HelpCircle className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </a>
        <button
          onClick={onSignOut}
          disabled={signingOut}
          title="Sign out"
          className="w-9 h-9 rounded-full flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast disabled:opacity-50"
        >
          <LogOut className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </button>
      </div>
    </header>
  );
}
