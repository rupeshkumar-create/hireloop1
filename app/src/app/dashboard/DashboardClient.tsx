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
import { fetchMyProfile } from "@/lib/api/profile";
import { type MatchedJob } from "@/lib/api/matches";
import { fetchIntros } from "@/lib/api/intros";
import { fetchSavedJobIds } from "@/lib/api/saved-jobs";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import { DashboardWelcomeBanner } from "@/components/dashboard/DashboardWelcomeBanner";
import { CoachingPanel } from "@/components/dashboard/CoachingPanel";
import { HomePanel } from "@/components/dashboard/HomePanel";
import { JobsPanel } from "@/components/dashboard/JobsPanel";
import { ProfilePanel } from "@/components/dashboard/ProfilePanel";
import { TopNav } from "@/components/dashboard/TopNav";
import { IntrosList } from "@/components/intros/IntrosList";
import { CandidateMobileNav } from "@/components/layout/CandidateMobileNav";
import { ChatPeekStrip } from "@/components/dashboard/ChatPeekStrip";
import { type JobsTab, type PanelId, PANEL_TITLE } from "@/lib/dashboard/panel-types";
import { useToast } from "@/components/ui";

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
  const [activeConvoId, setActiveConvoId] = useState<string | null>(initialConvoId ?? null);
  const [pendingIntros, setPendingIntros] = useState(false);
  const [activePanel, setActivePanel] = useState<PanelId | null>(initialPanel ?? null);
  const [signingOut, setSigningOut] = useState(false);
  const [injected, setInjected] = useState<{ text: string; nonce: number } | null>(null);
  const [savedJobIds, setSavedJobIds] = useState<Set<string>>(new Set());
  const [savedJobsRefreshKey, setSavedJobsRefreshKey] = useState(0);

  useEffect(() => {
    router.prefetch("/resumes");
    router.prefetch("/intros");
    router.prefetch("/dashboard?panel=jobs");

    let cancelled = false;

    fetchSavedJobIds()
      .then((ids) => {
        if (!cancelled) setSavedJobIds(ids);
      })
      .catch(() => {
        if (!cancelled) setSavedJobIds(new Set());
      });

    void fetchMyProfile().catch(() => {});
    void fetchIntros()
      .then((rows) => {
        if (!cancelled) {
          setPendingIntros(rows.some((r) => r.status === "pending"));
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [router]);

  function handleSavedChange(jobId: string, saved: boolean) {
    setSavedJobIds((prev) => {
      const next = new Set(prev);
      if (saved) next.add(jobId);
      else next.delete(jobId);
      return next;
    });
    setSavedJobsRefreshKey((k) => k + 1);
  }

  function syncDashboardUrl(panel: PanelId | null, jobsTab?: JobsTab) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
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

  function sendToChat(text: string) {
    openPanel(null);
    setInjected({ text, nonce: Date.now() });
  }

  function handleRequestIntro(job: MatchedJob) {
    if (!canApplyOrIntro) {
      toast.error("Upload a resume or add city + CTC to request intros.");
      openPanel("jobs");
      return;
    }
    sendToChat(
      `I'd like to request an intro for the "${job.title}" role at ${
        job.company_name ?? "this company"
      } (job ID: ${job.job_id}).`,
    );
  }

  function handleDirectApply(job: MatchedJob) {
    if (!canApplyOrIntro) {
      toast.error("Upload a resume or add city + CTC to apply.");
      openPanel("jobs");
      return;
    }
    if (job.apply_url) {
      window.open(job.apply_url, "_blank", "noopener,noreferrer");
    }
  }

  function handleProfileBoosted() {
    router.refresh();
  }

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
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
        <DashboardWelcomeBanner
          firstName={candidateName?.split(" ")[0]}
        />

        <div className="flex-1 min-h-0 flex overflow-hidden">
        {activePanel && (
          <div
            key={activePanel}
            className={cn(
              "flex flex-col bg-paper-0 overflow-hidden border-ink-100 animate-slide-in-left",
              "absolute inset-0 z-20 w-full",
              "lg:static lg:inset-auto lg:z-auto lg:w-[clamp(380px,42%,600px)] lg:flex-shrink-0 lg:border-r",
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

            <div className="flex-1 overflow-y-auto">
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
              {activePanel === "inbox" && <IntrosList variant="panel" />}
              {activePanel === "profile" && <ProfilePanel onSendToChat={sendToChat} />}
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
                  onAskAarya={() =>
                    sendToChat("Find me the best matching jobs for my profile right now.")
                  }
                />
              )}
              {activePanel === "coaching" && <CoachingPanel onSendToChat={sendToChat} />}
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
            injectedMessage={injected}
            className="h-full"
            onSessionCreated={(id) => setActiveConvoId(id)}
            savedJobIds={savedJobIds}
            onSavedChange={handleSavedChange}
            onRequestIntro={handleRequestIntro}
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
