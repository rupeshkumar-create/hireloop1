"use client";

/**
 * DashboardClient — Aarya home.
 *
 * Layout:
 *
 *   ┌──────────────────────────────────────────────────────┐
 *   │ [H]  Home  Jobs  Profile  Inbox  Coaching   Help  ⎋  │  ← top nav pills
 *   ├───────────────────────────┬──────────────────────────┤
 *   │  Preview panel (LEFT)     │  Chat (RIGHT)            │
 *   │  ← opens when pill active │  always visible          │
 *   │  [X] closes panel         │                          │
 *   └───────────────────────────┴──────────────────────────┘
 *
 * Top nav pills toggle their preview panel open/closed.
 * Chat is ALWAYS visible on the RIGHT — the preview panel opens on the LEFT.
 */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { X } from "@/components/brand/icons";
import { fetchMyProfile, inferMarketFromGeo } from "@/lib/api/profile";
import { type MatchedJob } from "@/lib/api/matches";
import { fetchIntros } from "@/lib/api/intros";
import { fetchSavedJobIds, saveJob, subscribeSavedJobs } from "@/lib/api/saved-jobs";
import { fetchMatchFeed, invalidateMatchFeedCache } from "@/lib/api/matches";
import { recordJobApplication } from "@/lib/api/job-applications";
import { createClient } from "@/lib/supabase/client";
import { clearClientOnboardingComplete, isClientOnboardingCompleteRecent } from "@/lib/auth/onboarding-complete";
import { cn } from "@/lib/utils";
import { CoachingPanel } from "@/components/dashboard/CoachingPanel";
import { HomePanel } from "@/components/dashboard/HomePanel";
import { JobsPanel } from "@/components/dashboard/JobsPanel";
import { ProfilePanel } from "@/components/dashboard/ProfilePanel";
import { SettingsPanel } from "@/components/dashboard/SettingsPanel";
import { CareerPathPanel } from "@/components/jobs/CareerPathPanel";
import { JobTrackerPanel } from "@/components/jobs/JobTrackerPanel";
import { TopNav } from "@/components/dashboard/TopNav";
import { IntrosInboxPanel } from "@/components/intros/IntrosInboxPanel";
import { CandidateMobileNav } from "@/components/layout/CandidateMobileNav";
import { ChatPeekStrip } from "@/components/dashboard/ChatPeekStrip";
import { type JobsTab, type PanelId, PANEL_TITLE } from "@/lib/dashboard/panel-types";
import { useToast } from "@/components/ui";
import type { KickoffResult } from "@/components/chat/CareerKickoffFlow";

const ChatInterface = dynamic(
  () =>
    import("@/components/chat/ChatInterface").then((m) => ({
      default: m.ChatInterface,
    })),
  {
    loading: () => (
      <div className="h-full min-h-[320px] rounded-xl bg-ink-50 animate-pulse" />
    ),
    ssr: false,
  },
);

interface DashboardClientProps {
  conversationId?: string;
  candidateName?: string;
  initialInput?: string;
  initialPanel?: PanelId;
  canApplyOrIntro?: boolean;
  hasResume?: boolean;
  hasVoiceSession?: boolean;
  showProfileBoosters?: boolean;
  initialVoiceDeepDive?: boolean;
  initialJobsTab?: JobsTab;
  showAdminLink?: boolean;
}

export function DashboardClient({
  conversationId: initialConvoId,
  candidateName,
  initialInput,
  initialPanel,
  canApplyOrIntro = true,
  hasResume = false,
  hasVoiceSession = false,
  showProfileBoosters = false,
  initialVoiceDeepDive = false,
  initialJobsTab,
  showAdminLink = false,
}: DashboardClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  // Post-onboarding guided flow (?kickoff=career) — read once on mount so the
  // wizard survives the URL cleanup below.
  const [initialKickoff, setInitialKickoff] = useState(
    () =>
      searchParams?.get("kickoff") === "career" ||
      isClientOnboardingCompleteRecent(),
  );
  const [activeConvoId, setActiveConvoId] = useState<string | null>(initialConvoId ?? null);
  const [pendingIntros, setPendingIntros] = useState(false);
  const [activePanel, setActivePanel] = useState<PanelId | null>(initialPanel ?? null);
  const [signingOut, setSigningOut] = useState(false);
  const [injected, setInjected] = useState<{ text: string; nonce: number } | null>(null);
  const [savedJobIds, setSavedJobIds] = useState<Set<string>>(new Set());
  const [savedJobsRefreshKey, setSavedJobsRefreshKey] = useState(0);
  const [kickoffMatchJobs, setKickoffMatchJobs] = useState<MatchedJob[] | null>(null);
  const [kickoffMatchTitle, setKickoffMatchTitle] = useState<string | null>(null);
  const [introWatch, setIntroWatch] = useState<{ jobId: string; nonce: number } | null>(null);
  const [handledIntroParam] = useState(() => ({ handled: false }));
  const [sendToChatRef] = useState(() => ({ fn: (_text: string) => Date.now() }));
  // Jobs Aarya surfaced in chat — mirrored into the Matches sidebar so the user
  // never has to click "Find jobs" to see them there.
  const [chatJobs, setChatJobs] = useState<MatchedJob[] | null>(null);

  // Allow deep-linking into an intro request from places like /jobs/[id].
  // Example: /dashboard?intro_job_id=...&intro_title=...&intro_company=...
  useEffect(() => {
    if (handledIntroParam.handled) return;
    const jobId = searchParams?.get("intro_job_id")?.trim();
    if (!jobId) return;
    handledIntroParam.handled = true;

    const title = searchParams?.get("intro_title")?.trim() || "this role";
    const company = searchParams?.get("intro_company")?.trim() || "this company";
    const nonce = sendToChatRef.fn(
      `I'd like to request an intro for the "${title}" role at ${company} (job ID: ${jobId}).`,
    );
    setIntroWatch({ jobId, nonce });

    const params = new URLSearchParams(searchParams?.toString() ?? "");
    params.delete("intro_job_id");
    params.delete("intro_title");
    params.delete("intro_company");
    const q = params.toString();
    router.replace(q ? `/dashboard?${q}` : "/dashboard", { scroll: false });
  }, [router, searchParams, handledIntroParam, sendToChatRef]);

  useEffect(() => {
    router.prefetch("/resumes");
    router.prefetch("/intros");
    router.prefetch("/dashboard?panel=jobs");
    router.prefetch("/dashboard?panel=career_path");
    router.prefetch("/dashboard?panel=tracker");
    router.prefetch("/dashboard?panel=settings");

    let cancelled = false;

    const syncSavedFromServer = () => {
      fetchSavedJobIds()
        .then((ids) => {
          if (!cancelled) setSavedJobIds(ids);
        })
        .catch(() => {
          if (!cancelled) setSavedJobIds(new Set());
        });
    };

    syncSavedFromServer();

    const unsubscribe = subscribeSavedJobs(() => {
      syncSavedFromServer();
      setSavedJobsRefreshKey((k) => k + 1);
    });

    const onFocus = () => syncSavedFromServer();
    window.addEventListener("focus", onFocus);

    void fetchMyProfile().catch(() => {});
    void inferMarketFromGeo().catch(() => {});
    invalidateMatchFeedCache();
    void fetchMatchFeed(undefined, { force: true }).catch(() => {});
    void fetchIntros()
      .then((rows) => {
        if (!cancelled) {
          setPendingIntros(rows.some((r) => r.status === "pending"));
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      unsubscribe();
      window.removeEventListener("focus", onFocus);
    };
  }, [router]);

  function handleSavedChange(jobId: string, saved: boolean) {
    setSavedJobIds((prev) => {
      const next = new Set(prev);
      if (saved) next.add(jobId);
      else next.delete(jobId);
      return next;
    });
  }

  function syncDashboardUrl(panel: PanelId | null, jobsTab?: JobsTab) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    params.delete("kickoff");
    if (panel) params.set("panel", panel);
    else params.delete("panel");
    if (panel === "jobs" && jobsTab && jobsTab !== "matches") {
      params.set("tab", jobsTab);
    } else {
      params.delete("tab");
    }
    const q = params.toString();
    router.replace(q ? `/dashboard?${q}` : "/dashboard", { scroll: false });
  }

  function openPanel(id: PanelId | null, jobsTab?: JobsTab) {
    setActivePanel(id);
    syncDashboardUrl(id, jobsTab);
  }

  function sendToChat(text: string): number {
    openPanel(null);
    const nonce = Date.now();
    setInjected({ text, nonce });
    return nonce;
  }

  // Keep a stable function ref for effects (avoids exhaustive-deps churn).
  sendToChatRef.fn = sendToChat;

  function handleCareerKickoffComplete(result: KickoffResult) {
    clearClientOnboardingComplete();
    setInitialKickoff(false);
    setKickoffMatchJobs(null);
    setKickoffMatchTitle(result.preferredTitle);
    syncDashboardUrl(activePanel);
  }

  function handleRequestIntro(job: MatchedJob) {
    if (!canApplyOrIntro) {
      toast.error("Upload a resume or add city + CTC to request intros.");
      openPanel("jobs");
      return;
    }
    handleSavedChange(job.job_id, true);
    void saveJob(job.job_id).catch(() => {
      /* Aarya intro path also bookmarks server-side */
    });
    const nonce = sendToChat(
      `I'd like to request an intro for the "${job.title}" role at ${
        job.company_name ?? "this company"
      } (job ID: ${job.job_id}).`,
    );
    setIntroWatch({ jobId: job.job_id, nonce });
  }

  function handleDirectApply(job: MatchedJob) {
    if (!canApplyOrIntro) {
      toast.error("Upload a resume or add city + CTC to apply.");
      openPanel("jobs");
      return;
    }
    handleSavedChange(job.job_id, true);
    void recordJobApplication(job.job_id)
      .then(() => {
        toast.success(`Marked as applied — tracked in Job tracker`);
      })
      .catch(() => {
        toast.error("Couldn't log application — try again from Job tracker");
      });
  }

  function handleProfileBoosted() {
    router.refresh();
  }

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      clearClientOnboardingComplete();
      await createClient().auth.signOut();
    } catch {
      /* fall through */
    } finally {
      window.location.href = "/login";
    }
  }

  useEffect(() => {
    const check = async () => {
      try {
        const rows = await fetchIntros({ force: true });
        setPendingIntros(rows.some((r) => r.status === "pending"));
      } catch {
        /* silent */
      }
    };
    const id = window.setInterval(check, 30_000);
    return () => window.clearInterval(id);
  }, []);

  function togglePanel(id: PanelId) {
    setActivePanel((cur) => {
      const next = cur === id ? null : id;
      syncDashboardUrl(next);
      return next;
    });
  }

  function setJobsTab(tab: JobsTab) {
    if (activePanel === "jobs") syncDashboardUrl("jobs", tab);
  }

  return (
    <div className="flex flex-col h-screen bg-paper-0 overflow-hidden pb-16 md:pb-0">
      <div className="flex min-h-0 flex-1 overflow-hidden">
      <TopNav
        activePanel={activePanel}
        onTogglePanel={togglePanel}
        pendingIntros={pendingIntros}
        showAdminLink={showAdminLink}
        onSignOut={() => void handleSignOut()}
        signingOut={signingOut}
      />

      <main id="main-content" className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden relative">
        <div className="flex-1 min-h-0 flex overflow-hidden">
        {activePanel && (
          <div
            key={activePanel}
            className={cn(
              "flex flex-col bg-paper-0 overflow-hidden border-ink-100 animate-slide-in-left",
              "absolute inset-0 z-20 w-full",
              "lg:static lg:inset-auto lg:z-auto lg:flex-shrink-0 lg:border-r",
              "lg:w-[clamp(380px,42%,600px)]",
            )}
          >
            <div className="flex items-center justify-between h-14 px-5 border-b border-ink-100 shrink-0">
              <h2 className="text-h3 font-semibold text-ink-900">
                {PANEL_TITLE[activePanel]}
              </h2>
              <button
                onClick={() => openPanel(null)}
                aria-label="Close panel"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast active:scale-95"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto">
              {activePanel === "home" && (
                <HomePanel
                  candidateName={candidateName}
                  showProfileBoosters={showProfileBoosters}
                  hasResume={hasResume}
                  hasVoiceSession={hasVoiceSession}
                  canApply={canApplyOrIntro}
                  onProfileBoosted={handleProfileBoosted}
                  onSendToChat={sendToChat}
                  onOpenPanel={openPanel}
                />
              )}
              {activePanel === "inbox" && (
                <div className="h-full min-h-0 overflow-hidden">
                  <IntrosInboxPanel />
                </div>
              )}
              {activePanel === "profile" && (
                <ProfilePanel onSendToChat={sendToChat} onOpenPanel={openPanel} />
              )}
              {activePanel === "jobs" && (
                <JobsPanel
                  conversationId={activeConvoId ?? undefined}
                  initialTab={initialJobsTab}
                  onTabChange={setJobsTab}
                  canApplyOrIntro={canApplyOrIntro}
                  showProfileBoosters={showProfileBoosters}
                  hasResume={hasResume}
                  hasVoiceSession={hasVoiceSession}
                  onProfileBoosted={handleProfileBoosted}
                  onRequestIntro={handleRequestIntro}
                  onDirectApply={handleDirectApply}
                  savedJobIds={savedJobIds}
                  onSavedChange={handleSavedChange}
                  savedJobsRefreshKey={savedJobsRefreshKey}
                  kickoffJobs={chatJobs ?? kickoffMatchJobs}
                  kickoffTitle={kickoffMatchTitle}
                  onAskAarya={() =>
                    sendToChat("Find me the best matching roles for my profile right now.")
                  }
                  pendingIntros={pendingIntros}
                />
              )}
              {activePanel === "career_path" && (
                <CareerPathPanel
                  conversationId={activeConvoId ?? undefined}
                  onRequestIntro={handleRequestIntro}
                  onDirectApply={handleDirectApply}
                  savedJobIds={savedJobIds}
                  onSavedChange={handleSavedChange}
                  className="h-full"
                />
              )}
              {activePanel === "tracker" && <JobTrackerPanel className="h-full" />}
              {activePanel === "coaching" && <CoachingPanel onSendToChat={sendToChat} />}
              {activePanel === "settings" && (
                <SettingsPanel
                  onEditProfile={() => openPanel("profile")}
                  onSignOut={() => void handleSignOut()}
                  signingOut={signingOut}
                />
              )}
            </div>
          </div>
        )}

        <div
          className={cn(
            "overflow-hidden transition-[flex-basis] duration-base ease-out-soft",
            activePanel ? "flex-1 min-w-0" : "w-full",
          )}
        >
          <ChatInterface
            conversationId={activeConvoId}
            initialInput={initialInput}
            candidateName={candidateName}
            initialVoiceDeepDive={initialVoiceDeepDive}
            initialKickoff={initialKickoff}
            injectedMessage={injected}
            introWatch={introWatch}
            className="h-full"
            onSessionCreated={(id) => setActiveConvoId(id)}
            savedJobIds={savedJobIds}
            onSavedChange={handleSavedChange}
            onRequestIntro={handleRequestIntro}
            onCareerKickoffComplete={handleCareerKickoffComplete}
            onJobsFound={setChatJobs}
          />
        </div>
        </div>
      </main>
      </div>

      {activePanel && (
        <ChatPeekStrip onOpenChat={() => openPanel(null)} />
      )}

      <CandidateMobileNav activePanel={activePanel} onTogglePanel={togglePanel} />
    </div>
  );
}
