"use client";

/**
 * AppShell — unified authenticated layout (DESIGN.md §6).
 * Uses shared CANDIDATE_NAV from @/lib/candidate-nav.
 */

import { type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings } from "lucide-react";
import { CandidateMobileNav } from "@/components/layout/CandidateMobileNav";
import {
  CANDIDATE_NAV,
  type CandidateNavId,
} from "@/lib/candidate-nav";
import { Avatar } from "@/components/ui";
import { BackToAaryaLink, ContextHeader } from "@/components/ux";
import { RoleSwitchButton } from "@/components/layout/RoleSwitchButton";
import { cn } from "@/lib/utils";

export type AppShellProps = {
  title: string;
  action?: ReactNode;
  width?: "form" | "feed";
  activeNav?: CandidateNavId;
  userName?: string;
  userAvatarUrl?: string | null;
  profileCompleteness?: number | null;
  matchCount?: number | null;
  location?: string | null;
  backContext?: string;
  children: ReactNode;
};

export function AppShell({
  title,
  action,
  width = "form",
  activeNav,
  userName,
  userAvatarUrl,
  profileCompleteness,
  matchCount,
  location,
  backContext,
  children,
}: AppShellProps) {
  const pathname = usePathname();

  const isActive = (item: (typeof CANDIDATE_NAV)[number]) => {
    if (activeNav === item.id) return true;
    const base = item.href.split("?")[0];
    if (pathname === base) {
      if (item.id === "matches" && pathname === "/dashboard") return false;
      return true;
    }
    return item.match?.some((m) => pathname?.startsWith(m)) ?? false;
  };

  const contentWidth = width === "feed" ? "max-w-6xl" : "max-w-3xl";

  return (
    <div className="flex h-screen flex-col bg-paper-0 overflow-hidden">
      <ContextHeader
        name={userName}
        location={location}
        profileCompleteness={profileCompleteness}
        matchCount={matchCount}
      />
      <div className="flex min-h-0 flex-1">
        <aside className="hidden md:flex w-16 shrink-0 flex-col items-center border-r border-ink-100 bg-paper-1 py-3">
          <Link
            href="/dashboard"
            aria-label="Hireloop home"
            className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-ink-900"
          >
            <span className="text-small font-semibold text-paper-0">H</span>
          </Link>
          <nav className="flex flex-1 flex-col items-center gap-1">
            {CANDIDATE_NAV.map((item) => (
              <RailLink key={item.id} item={item} active={isActive(item)} />
            ))}
          </nav>
          <div className="mt-2 flex flex-col items-center gap-1">
            <Link
              href="/settings"
              title="Settings"
              aria-label="Settings"
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-fast",
                pathname === "/settings"
                  ? "bg-ink-900 text-paper-0"
                  : "text-ink-500 hover:bg-ink-50 hover:text-ink-900",
              )}
            >
              <Settings className="h-[18px] w-[18px]" strokeWidth={1.5} />
            </Link>
            <Link href="/profile" title="Profile" aria-label="Profile">
              <Avatar name={userName ?? ""} src={userAvatarUrl} size="md" />
            </Link>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-ink-100 bg-paper-1 px-4 md:px-6">
            <div className="min-w-0">
              {backContext && (
                <div className="mb-0.5">
                  <BackToAaryaLink context={backContext} />
                </div>
              )}
              <h1 className="truncate text-h2 text-ink-900">{title}</h1>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <RoleSwitchButton to="recruiter" target="/recruiter" />
              {action}
            </div>
          </header>
          <main id="main-content" className="flex-1 overflow-y-auto bg-paper-0 px-4 pb-24 pt-6 md:px-6 md:pb-10">
            <div className={cn("mx-auto w-full", contentWidth)}>{children}</div>
          </main>
        </div>
      </div>

      <CandidateMobileNav />
    </div>
  );
}

function RailLink({
  item,
  active,
}: {
  item: (typeof CANDIDATE_NAV)[number];
  active: boolean;
}) {
  return (
    <Link
      href={item.href}
      title={item.label}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-fast",
        active ? "bg-ink-900 text-paper-0" : "text-ink-500 hover:bg-ink-50 hover:text-ink-900",
      )}
    >
      <item.Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
    </Link>
  );
}
