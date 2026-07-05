"use client";

/**
 * RecruiterShell — persistent nav for the recruiter workspace.
 */

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowLeftRight,
  Kanban,
  Loader2,
  Plus,
  Settings,
} from "@/components/brand/icons";
import { switchActiveRole } from "@/lib/api/role";
import {
  RECRUITER_NAV,
  type RecruiterNavItem,
} from "@/lib/recruiter-nav";
import { RecruiterMobileNav } from "@/components/layout/RecruiterMobileNav";
import { useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

type RecruiterShellProps = {
  children: React.ReactNode;
};

export function RecruiterShell({ children }: RecruiterShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { toast } = useToast();
  const [switching, setSwitching] = useState(false);

  if (pathname?.startsWith("/recruiter/onboarding")) {
    return <>{children}</>;
  }

  const fullBleed = Boolean(
    pathname?.match(/\/recruiter\/roles\/[^/]+\/(intake|pipeline)/)
  );

  const switchToCandidate = async () => {
    if (switching) return;
    setSwitching(true);
    try {
      await switchActiveRole("candidate");
      router.push("/dashboard");
    } catch {
      toast.error("Couldn't switch roles — try again");
      setSwitching(false);
    }
  };

  const isActive = (item: RecruiterNavItem) =>
    pathname === item.href ||
    (item.match?.some((m) => pathname?.startsWith(m)) ?? false);

  return (
    <div className="flex h-screen bg-paper-0 overflow-hidden">
      <aside className="hidden md:flex w-16 shrink-0 flex-col items-center border-r border-ink-100 bg-paper-1 py-3">
        <Link
          href="/recruiter/inbox"
          aria-label="Hireloop recruiter"
          className="mb-4 flex h-9 w-9 items-center justify-center rounded-xl bg-ink-900"
        >
          <span className="text-small font-semibold text-paper-0">N</span>
        </Link>

        <nav className="flex flex-1 flex-col items-center gap-1">
          {RECRUITER_NAV.map((item) => (
            <Link
              key={item.id}
              href={item.href!}
              title={item.label}
              aria-label={item.label}
              aria-current={isActive(item) ? "page" : undefined}
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-xl transition-colors duration-fast",
                isActive(item)
                  ? "bg-ink-900 text-paper-0"
                  : "text-ink-500 hover:bg-ink-50 hover:text-ink-900"
              )}
            >
              <item.Icon className="h-[18px] w-[18px]" strokeWidth={1.5} />
            </Link>
          ))}
        </nav>

        <div className="mt-2 flex flex-col items-center gap-1">
          <button
            type="button"
            onClick={() => void switchToCandidate()}
            disabled={switching}
            title="Switch to candidate view"
            aria-label="Switch to candidate view"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-ink-400 hover:bg-ink-50 hover:text-ink-900 transition-colors disabled:opacity-50"
          >
            {switching ? (
              <Loader2 className="h-[18px] w-[18px] animate-spin" strokeWidth={1.5} />
            ) : (
              <ArrowLeftRight className="h-[18px] w-[18px]" strokeWidth={1.5} />
            )}
          </button>
          <Link
            href="/recruiter/roles/new"
            title="New role"
            aria-label="New role"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-ink-400 hover:bg-ink-50 hover:text-ink-900 transition-colors"
          >
            <Plus className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </Link>
          <Link
            href="/recruiter/settings"
            title="Settings"
            aria-label="Settings"
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-xl transition-colors",
              pathname === "/recruiter/settings"
                ? "bg-ink-900 text-paper-0"
                : "text-ink-400 hover:bg-ink-50 hover:text-ink-900"
            )}
          >
            <Settings className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </Link>
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
