"use client";

/**
 * RecruiterShell — persistent nav for the recruiter workspace.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Briefcase,
  Inbox,
  Kanban,
  Plus,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavId = "inbox" | "roles" | "settings";

type NavItem = {
  id: NavId;
  label: string;
  href: string;
  Icon: LucideIcon;
  match?: string[];
};

const NAV_ITEMS: NavItem[] = [
  { id: "inbox", label: "Inbox", href: "/recruiter/inbox", Icon: Inbox },
  {
    id: "roles",
    label: "Roles",
    href: "/recruiter/roles",
    Icon: Briefcase,
    match: ["/recruiter/roles"],
  },
];

type RecruiterShellProps = {
  children: React.ReactNode;
};

export function RecruiterShell({ children }: RecruiterShellProps) {
  const pathname = usePathname();
  const fullBleed = Boolean(
    pathname?.match(/\/recruiter\/roles\/[^/]+\/(intake|pipeline)/)
  );

  const isActive = (item: NavItem) =>
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
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.id}
              href={item.href}
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

      <nav className="fixed inset-x-0 bottom-0 z-20 flex h-16 items-center justify-around border-t border-ink-100 bg-paper-1 md:hidden">
        {NAV_ITEMS.map((item) => {
          const active = isActive(item);
          return (
            <Link
              key={item.id}
              href={item.href}
              className={cn(
                "flex flex-col items-center gap-0.5 px-2 py-1",
                active ? "text-ink-900" : "text-ink-400"
              )}
            >
              <item.Icon className="h-5 w-5" strokeWidth={1.5} />
              <span className="text-micro font-medium">{item.label}</span>
            </Link>
          );
        })}
        <Link
          href="/recruiter/roles/new"
          className="flex flex-col items-center gap-0.5 px-2 py-1 text-ink-400"
        >
          <Plus className="h-5 w-5" strokeWidth={1.5} />
          <span className="text-micro font-medium">New</span>
        </Link>
      </nav>
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
