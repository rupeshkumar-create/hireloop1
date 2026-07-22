"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { MatchedJob } from "@/lib/api/matches";
import type { JobsTab } from "@/lib/dashboard/panel-types";
import { MatchFeed } from "@/components/jobs/MatchFeed";
import { SavedJobsPanel } from "@/components/jobs/SavedJobsPanel";
import { JobTrackerPanel } from "@/components/jobs/JobTrackerPanel";
import { JobsQueueStatusBar } from "@/components/jobs/JobsQueueStatusBar";
import { ProfileBoosters } from "@/components/onboarding/ProfileBoosters";
import { ScheduleCareerCall } from "@/components/chat/ScheduleCareerCall";
import { Calendar, Phone } from "@/components/brand/icons";
import { Button } from "@/components/ui";
import { BTN_PRIMARY } from "@/lib/button-classes";
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
  kickoffJobs?: MatchedJob[] | null;
  kickoffTitle?: string | null;
  onAskAarya?: () => void;
  pendingIntros?: boolean;
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
  kickoffJobs,
  kickoffTitle,
  onAskAarya,
  pendingIntros = false,
}: JobsPanelProps) {
  const [tab, setTab] = useState<JobsTab>(initialTab ?? "matches");
  const [kitsReadyCount, setKitsReadyCount] = useState(0);
  const [schedulingCareerCall, setSchedulingCareerCall] = useState(false);

  function selectTab(next: JobsTab) {
    setTab(next);
    onTabChange?.(next);
  }

  // Keep the local tab in sync when the URL explicitly changes (?tab=saved).
  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    if (!kickoffTitle && !kickoffJobs?.length) return;
    setTab("matches");
  }, [kickoffJobs?.length, kickoffTitle]);

  // One helper strip at a time: boosters when gated, else queue status.
  const showBoosters = Boolean(showProfileBoosters);

  return (
    <div className="flex flex-col h-full min-h-0">
      {showBoosters && (
        <div className="p-5 pb-0 shrink-0">
          <ProfileBoosters
            hasResume={hasResume ?? false}
            hasVoiceSession={hasVoiceSession ?? false}
            canApply={canApplyOrIntro ?? true}
            onProfileUpdated={onProfileBoosted}
          />
        </div>
      )}

      <section className="shrink-0 border-b border-ink-100 px-5 py-4" aria-labelledby="career-call-heading">
        <div className="space-y-3">
          <div>
            <h3 id="career-call-heading" className="text-small font-semibold text-ink-900">
              15-minute career call with Aarya
            </h3>
            <p className="mt-1 text-micro text-ink-600">
              Your transcript stays private. Audio is not saved.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/dashboard?voice=deep&panel=jobs"
              className={cn(BTN_PRIMARY, "h-9 gap-2 px-3 text-small")}
            >
              <Phone className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
              Start now
            </Link>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSchedulingCareerCall((current) => !current)}
              leftIcon={<Calendar className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />}
              aria-expanded={schedulingCareerCall}
              aria-controls="career-call-scheduler"
            >
              Schedule for later
            </Button>
          </div>
          {schedulingCareerCall && (
            <div id="career-call-scheduler">
              <ScheduleCareerCall />
            </div>
          )}
        </div>
      </section>

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
        <button
          type="button"
          onClick={() => selectTab("applied")}
          className={cn(
            "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "applied"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700",
          )}
        >
          Applied
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
            seedJobs={kickoffJobs}
            seedTitle={kickoffTitle}
            compact
            className="h-full p-5"
          />
        ) : tab === "saved" ? (
          <SavedJobsPanel
            conversationId={conversationId}
            onRequestIntro={onRequestIntro}
            savedJobIds={savedJobIds}
            onSavedChange={onSavedChange}
            refreshKey={savedJobsRefreshKey}
            onKitsReadyCountChange={setKitsReadyCount}
            className="h-full flex flex-col"
          />
        ) : (
          <JobTrackerPanel className="h-full p-5" />
        )}
      </div>

      {!showBoosters && (
        <JobsQueueStatusBar
          savedCount={savedJobIds.size}
          kitsReadyCount={kitsReadyCount}
          pendingIntros={pendingIntros}
          onOpenSaved={() => selectTab("saved")}
        />
      )}
    </div>
  );
}
