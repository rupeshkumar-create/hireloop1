"use client";

/**
 * RoleWorkspaceTabs — one persistent header for everything about a role.
 *
 * A role used to be three disconnected pages (intake chat, brief, pipeline)
 * with one-off back arrows between them. This bar makes them tabs of a single
 * workspace so the recruiter always knows where they are and what else exists.
 */

import Link from "next/link";
import { ArrowLeft } from "@/components/brand/icons";
import { ShareRoleLink } from "@/components/recruiter/ShareRoleLink";
import { cn } from "@/lib/utils";

export type RoleTab = "chat" | "brief" | "market" | "ops" | "pipeline";

const TABS: { id: RoleTab; label: string; path: string; hint: string }[] = [
  { id: "chat", label: "Nitya chat", path: "intake", hint: "Refine the role and search candidates" },
  { id: "brief", label: "Brief", path: "brief", hint: "Edit title, JD, comp, must-haves" },
  { id: "market", label: "Market", path: "market", hint: "Comp bands, competitors, skill gaps" },
  { id: "ops", label: "Hiring ops", path: "ops", hint: "Interview kit, scheduling, nudges" },
  { id: "pipeline", label: "Pipeline", path: "pipeline", hint: "Track candidates across stages" },
];

export function RoleWorkspaceTabs({
  roleId,
  active,
  title,
  publicRoleUrl,
}: {
  roleId: string;
  active: RoleTab;
  title?: string | null;
  /** When the role is published, Share (copy public link) shows in the bar. */
  publicRoleUrl?: string | null;
}) {
  return (
    <div className="shrink-0 border-b border-ink-100 bg-paper-1 px-4">
      <div className="max-w-5xl mx-auto flex items-center gap-3 h-11">
        <Link
          href="/recruiter/roles"
          aria-label="All roles"
          title="All roles"
          className="flex items-center gap-1 text-ink-500 hover:text-ink-900 transition-colors -ml-1 p-1"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
        </Link>
        {title && (
          <p className="hidden sm:block text-small font-medium text-ink-900 truncate max-w-[220px]">
            {title}
          </p>
        )}
        <nav className="flex items-center gap-1 ml-auto sm:ml-4" aria-label="Role sections">
          {TABS.map((tab) => (
            <Link
              key={tab.id}
              href={`/recruiter/roles/${roleId}/${tab.path}`}
              title={tab.hint}
              aria-current={active === tab.id ? "page" : undefined}
              className={cn(
                "px-3 py-1.5 rounded-md text-small transition-colors",
                active === tab.id
                  ? "bg-ink-900 text-paper-0 font-medium"
                  : "text-ink-500 hover:text-ink-900 hover:bg-ink-50",
              )}
            >
              {tab.label}
            </Link>
          ))}
        </nav>
        {publicRoleUrl && (
          <ShareRoleLink publicRoleUrl={publicRoleUrl} className="hidden sm:block" />
        )}
      </div>
    </div>
  );
}
