"use client";

import { useEffect, useState } from "react";
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
  const [tab, setTab] = useState<JobsTab>(initialTab ?? "matches");

  function selectTab(next: JobsTab) {
    setTab(next);
    onTabChange?.(next);
  }

  // Keep the local tab in sync when the URL explicitly changes (?tab=path/saved).
  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

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
          onClick={() => selectTab("matches")}
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
