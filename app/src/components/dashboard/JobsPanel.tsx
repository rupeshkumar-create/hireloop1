"use client";

import { useEffect, useState } from "react";
import { fetchCareerPath } from "@/lib/api/career";
import type { MatchedJob } from "@/lib/api/matches";
import type { JobsTab } from "@/lib/dashboard/panel-types";
import { CareerPathPanel } from "@/components/jobs/CareerPathPanel";
import { MatchFeed } from "@/components/jobs/MatchFeed";
import { SavedJobsPanel } from "@/components/jobs/SavedJobsPanel";
import { ProfileBoosters } from "@/components/onboarding/ProfileBoosters";
import { cn } from "@/lib/utils";

export type JobsPanelProps = {
  conversationId?: string;
  initialTab?: JobsTab;
  onTabChange?: (tab: JobsTab) => void;
  canApplyOrIntro?: boolean;
  showProfileBoosters?: boolean;
  hasResume?: boolean;
  hasVoiceSession?: boolean;
  onProfileBoosted?: () => void;
  onRequestIntro: (job: MatchedJob) => void;
  onDirectApply: (job: MatchedJob) => void;
  savedJobIds: Set<string>;
  onSavedChange: (jobId: string, saved: boolean) => void;
  savedJobsRefreshKey: number;
  onAskAarya?: () => void;
};

export function JobsPanel({
  conversationId,
  initialTab,
  onTabChange,
  canApplyOrIntro,
  showProfileBoosters,
  hasResume,
  hasVoiceSession,
  onProfileBoosted,
  onRequestIntro,
  onDirectApply,
  savedJobIds,
  onSavedChange,
  savedJobsRefreshKey,
  onAskAarya,
}: JobsPanelProps) {
  const [tab, setTab] = useState<JobsTab>(initialTab ?? "path");
  const [pathChosen, setPathChosen] = useState<boolean | null>(null);

  function selectTab(next: JobsTab) {
    setTab(next);
    onTabChange?.(next);
  }

  function refreshPathChosen() {
    fetchCareerPath()
      .then((p) => setPathChosen(!!p?.prioritized_title))
      .catch(() => setPathChosen(false));
  }

  // Career-path-first: returning users land on matches; new users on paths.
  // Skip auto-switch when the URL already specifies a tab (?tab=).
  useEffect(() => {
    if (initialTab) return;
    let cancelled = false;
    fetchCareerPath()
      .then((p) => {
        if (cancelled) return;
        const chosen = !!p?.prioritized_title;
        setPathChosen(chosen);
        if (chosen) selectTab("matches");
      })
      .catch(() => {
        if (!cancelled) setPathChosen(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full">
      {showProfileBoosters && (
        <div className="p-5 pb-0 shrink-0">
          <ProfileBoosters
            hasResume={hasResume ?? false}
            hasVoiceSession={hasVoiceSession ?? false}
            canApply={canApplyOrIntro ?? true}
            onProfileUpdated={onProfileBoosted}
          />
        </div>
      )}

      <div className="flex items-center gap-1 px-5 pt-4 border-b border-ink-100 shrink-0">
        <button
          type="button"
          onClick={() => {
            selectTab("matches");
            refreshPathChosen();
          }}
          className={cn(
            "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "matches"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700",
          )}
        >
          Matches
        </button>
        <button
          type="button"
          onClick={() => selectTab("path")}
          className={cn(
            "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "path"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700",
          )}
        >
          Career paths
        </button>
        <button
          type="button"
          onClick={() => selectTab("saved")}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "saved"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700",
          )}
        >
          Saved
          {savedJobIds.size > 0 && (
            <span className="min-w-[1.25rem] h-5 px-1 rounded-full bg-ink-100 text-micro font-medium text-ink-600 flex items-center justify-center">
              {savedJobIds.size}
            </span>
          )}
        </button>
      </div>

      <div key={tab} className="flex-1 min-h-0 overflow-hidden animate-fade-in">
        {tab === "matches" ? (
          pathChosen === false ? (
            <div className="h-full p-5 flex flex-col items-center justify-center text-center gap-3">
              <p className="text-h3 text-ink-900">Let&apos;s aim your search</p>
              <p className="text-small text-ink-500 max-w-xs">
                Pick a career direction and I&apos;ll surface roles tailored to it — sharper than a
                generic list.
              </p>
              <button
                type="button"
                onClick={() => selectTab("path")}
                className="rounded-lg bg-ink-900 px-4 py-2 text-small font-medium text-paper-0 hover:bg-ink-800"
              >
                View career paths
              </button>
            </div>
          ) : (
            <MatchFeed
              conversationId={conversationId}
              onRequestIntro={onRequestIntro}
              onDirectApply={onDirectApply}
              applyLocked={!canApplyOrIntro}
              matchSourceBadge={!hasResume ? "linkedin" : undefined}
              savedJobIds={savedJobIds}
              onSavedChange={onSavedChange}
              onAskAarya={onAskAarya}
              className="h-full p-5"
            />
          )
        ) : tab === "path" ? (
          <CareerPathPanel
            conversationId={conversationId}
            onRequestIntro={onRequestIntro}
            savedJobIds={savedJobIds}
            onSavedChange={onSavedChange}
            className="h-full"
          />
        ) : (
          <SavedJobsPanel
            conversationId={conversationId}
            onRequestIntro={onRequestIntro}
            savedJobIds={savedJobIds}
            onSavedChange={onSavedChange}
            refreshKey={savedJobsRefreshKey}
            className="h-full p-5 flex flex-col"
          />
        )}
      </div>
    </div>
  );
}
