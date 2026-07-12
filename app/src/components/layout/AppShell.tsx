"use client";

/**
 * AppShell — standalone candidate pages. Same rail as dashboard; light page chrome
 * so it doesn’t compete with the drawer pattern.
 */

import { type ReactNode } from "react";
import { CandidateMobileNav } from "@/components/layout/CandidateMobileNav";
import { CandidateSidebar } from "@/components/layout/CandidateSidebar";
import { BackToAaryaLink } from "@/components/ux";
import { useCandidateShell } from "@/hooks/useCandidateShell";
import { cn } from "@/lib/utils";

export type AppShellProps = {
  title: string;
  action?: ReactNode;
  width?: "form" | "feed";
  backContext?: string;
  children: ReactNode;
};

export function AppShell({
  title,
  action,
  width = "form",
  backContext,
  children,
}: AppShellProps) {
  const { pendingIntros, signingOut, signOut } = useCandidateShell();
  const contentWidth = width === "feed" ? "max-w-6xl" : "max-w-3xl";

  return (
    <div className="flex h-screen flex-col bg-paper-0 overflow-hidden pb-16 md:pb-0">
      <div className="flex min-h-0 flex-1">
        <CandidateSidebar
          pendingIntros={pendingIntros}
          onSignOut={() => void signOut()}
          signingOut={signingOut}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <main
            id="main-content"
            className="flex-1 overflow-y-auto bg-paper-0 px-4 pt-5 pb-10 md:px-6"
          >
            <div className={cn("mx-auto w-full space-y-4", contentWidth)}>
              <div className="flex items-end justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  {backContext && <BackToAaryaLink context={backContext} />}
                  <h1 className="truncate text-h2 text-ink-900">{title}</h1>
                </div>
                {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
              </div>
              {children}
            </div>
          </main>
        </div>
      </div>

      <CandidateMobileNav />
    </div>
  );
}
