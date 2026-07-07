"use client";

/**
 * RecruiterShell — persistent navigation for the recruiter workspace.
 *
 * Labeled sidebar, not an icon rail: every destination is readable at a
 * glance (Home / Roles / Talent / Messages / Settings), "New role" is the
 * one primary action, and Messages carries a pending-intros badge. The old
 * 64px icon-only rail made options invisible unless you hovered each one.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Briefcase,
  Home,
  Inbox,
  Kanban,
  LogOut,
  Plus,
  Settings,
  Users,
} from "@/components/brand/icons";
import { RoleSwitchButton } from "@/components/layout/RoleSwitchButton";
import { RecruiterMobileNav } from "@/components/layout/RecruiterMobileNav";
import { useRecruiterShell } from "@/hooks/useRecruiterShell";
import { fetchRecruiterDashboard } from "@/lib/api/recruiter";
import { cn } from "@/lib/utils";

type RecruiterShellProps = {
  children: React.ReactNode;
};

type NavEntry = {
  id: string;
  label: string;
  href: string;
  Icon: React.ElementType;
  match?: string[];
  badge?: number;
};

export function RecruiterShell({ children }: RecruiterShellProps) {
  const pathname = usePathname();
  const { signingOut, signOut } = useRecruiterShell();
  const [pendingIntros, setPendingIntros] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchRecruiterDashboard()
      .then((d) => {
        if (!cancelled) setPendingIntros(d.stats?.pending_intros ?? 0);
      })
      .catch(() => {
        /* badge is a hint, never a blocker */
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (pathname?.startsWith("/recruiter/onboarding")) {
    return <>{children}</>;
  }

  const fullBleed = Boolean(
    pathname?.match(/\/recruiter\/(inbox|roles\/[^/]+\/(intake|pipeline))/)
  );

  const nav: NavEntry[] = [
    { id: "home", label: "Home", href: "/recruiter", Icon: Home },
    {
      id: "roles",
      label: "Roles",
      href: "/recruiter/roles",
      Icon: Briefcase,
      match: ["/recruiter/roles"],
    },
    {
      id: "talent",
      label: "Talent",
      href: "/recruiter/candidates",
      Icon: Users,
      match: ["/recruiter/candidates"],
    },
    {
      id: "messages",
      label: "Messages",
      href: "/recruiter/inbox",
      Icon: Inbox,
      match: ["/recruiter/inbox"],
      badge: pendingIntros,
    },
  ];

  const isActive = (item: NavEntry) => {
    if (item.id === "home") return pathname === "/recruiter";
    return (
      pathname === item.href ||
      (item.match?.some((m) => pathname?.startsWith(m)) ?? false)
    );
  };

  const rowClass = (active: boolean) =>
    cn(
      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-small font-medium transition-colors duration-fast",
      active
        ? "bg-ink-900 text-paper-0"
        : "text-ink-600 hover:bg-ink-50 hover:text-ink-900"
    );

  return (
    <div className="flex h-screen bg-paper-0 overflow-hidden">
      <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-ink-100 bg-paper-1 px-3 py-4">
        {/* Brand */}
        <Link href="/recruiter" className="flex items-center gap-2.5 px-2 mb-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-900">
            <span className="text-small font-semibold text-paper-0">N</span>
          </span>
          <span className="min-w-0">
            <span className="block text-small font-semibold text-ink-900 leading-tight">
              Hireschema
            </span>
            <span className="block text-micro text-ink-400 leading-tight">
              Recruiter workspace
            </span>
          </span>
        </Link>

        {/* Primary action */}
        <Link
          href="/recruiter/roles/new"
          className="flex items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2.5 text-small font-semibold text-on-accent hover:bg-accent-hover transition-colors mb-5"
        >
          <Plus className="h-4 w-4" strokeWidth={2} />
          New role
        </Link>

        {/* Workspace nav */}
        <p className="px-3 mb-1 text-micro font-medium uppercase tracking-wide text-ink-400">
          Workspace
        </p>
        <nav className="flex flex-col gap-0.5" aria-label="Recruiter navigation">
          {nav.map((item) => (
            <Link
              key={item.id}
              href={item.href}
              aria-current={isActive(item) ? "page" : undefined}
              className={rowClass(isActive(item))}
            >
              <item.Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
              <span className="flex-1 truncate">{item.label}</span>
              {item.badge ? (
                <span className="rounded-full bg-accent px-1.5 py-0.5 text-[10px] font-semibold text-on-accent leading-none">
                  {item.badge > 9 ? "9+" : item.badge}
                </span>
              ) : null}
            </Link>
          ))}
        </nav>

        <div className="flex-1" />

        {/* Account */}
        <p className="px-3 mb-1 text-micro font-medium uppercase tracking-wide text-ink-400">
          Account
        </p>
        <div className="flex flex-col gap-0.5">
          <Link
            href="/recruiter/settings"
            aria-current={pathname === "/recruiter/settings" ? "page" : undefined}
            className={rowClass(pathname === "/recruiter/settings")}
          >
            <Settings className="h-4 w-4 shrink-0" strokeWidth={1.5} />
            Settings
          </Link>
          <RoleSwitchButton to="candidate" target="/dashboard" variant="row" />
          <button
            type="button"
            onClick={() => void signOut()}
            disabled={signingOut}
            className={cn(rowClass(false), "disabled:opacity-50 text-left w-full")}
          >
            <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.5} />
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col min-h-0">
        {fullBleed ? (
          <div className="flex-1 min-h-0 flex flex-col">{children}</div>
        ) : (
          <main className="flex-1 overflow-y-auto pb-20 md:pb-0">{children}</main>
        )}
      </div>

      <RecruiterMobileNav />
    </div>
  );
}

export function PipelineLink({
  roleId,
  className,
}: {
  roleId: string;
  className?: string;
}) {
  return (
    <Link
      href={`/recruiter/roles/${roleId}/pipeline`}
      className={cn(
        "inline-flex items-center gap-1.5 text-small text-ink-600 hover:text-ink-900",
        className
      )}
    >
      <Kanban className="h-3.5 w-3.5" strokeWidth={1.5} />
      Pipeline
    </Link>
  );
}
