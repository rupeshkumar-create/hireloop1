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
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bell,
  Briefcase,
  Check,
  Circle,
  Building2,
  ChevronRight,
  Eye,
  EyeOff,
  FileText,
  GraduationCap,
  HelpCircle,
  Home,
  IndianRupee,
  Linkedin,
  Loader2,
  LogOut,
  MessageCircle,
  Inbox,
  MapPin,
  Phone,
  Search,
  Shield,
  SlidersHorizontal,
  Sparkles,
  User,
  X,
} from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import {
  applyProfileToForm,
  fetchMyProfile,
  getCachedProfile,
  invalidateProfileCache,
  REMOTE_PREFERENCE_OPTIONS,
  updateProfileVisibility,
  updateRemotePreference,
  type CandidateVisibility,
  type RemotePreference,
  type Education,
  type MyProfileData,
  type WorkExperience,
} from "@/lib/api/profile";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeed,
  fetchMatchFeedCount,
  getCachedMatchFeedCount,
  type MatchedJob,
} from "@/lib/api/matches";
import {
  cancelIntro,
  fetchIntros,
  getCachedIntros,
  type IntroRequest,
} from "@/lib/api/intros";
import { fetchSavedJobIds } from "@/lib/api/saved-jobs";
import { MatchFeed } from "@/components/jobs/MatchFeed";
import { SavedJobsPanel } from "@/components/jobs/SavedJobsPanel";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import { ChatInterface } from "@/components/chat/ChatInterface";
import { ResumeUpload } from "@/components/resume/ResumeUpload";
import { CareerPathPanel } from "@/components/jobs/CareerPathPanel";
import { CareerPathOptionCards } from "@/components/career/CareerPathOptionCards";
import { NextBestStep } from "@/components/dashboard/NextBestStep";
import { fetchCareerPath } from "@/lib/api/career";
import { CareerIntelligencePanel } from "@/components/profile/CareerIntelligencePanel";
import { GoogleConnectCard } from "@/components/profile/GoogleConnectCard";
import {
  IntelligenceHero,
  MatchesUnlockGate,
  NotificationDrawer,
} from "@/components/ux";
import { fetchCareerIntelligence } from "@/lib/api/career";
import { FadeUp } from "@/components/ui/motion";
import { fetchGoogleStatus } from "@/lib/api/gmail";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  EmptyState,
  useToast,
} from "@/components/ui";

// ── Panel type ────────────────────────────────────────────────────────────────

type PanelId = "home" | "inbox" | "profile" | "jobs" | "coaching";

const PANEL_TITLE: Record<PanelId, string> = {
  home:     "Mission control",
  inbox:    "Intros",
  profile:  "Profile",
  jobs:     "Matches",
  coaching: "Coaching",
};

// ── Notification categories (client-defined, never from API keys) ─────────────

type NotifCat = { id: string; label: string; desc: string };

const NOTIFICATION_CATEGORIES: NotifCat[] = [
  { id: "job_match_alerts",    label: "Job match alerts",      desc: "New jobs matching your profile"               },
  { id: "intro_updates",       label: "Intro request updates", desc: "When a recruiter responds to your intro"      },
  { id: "interview_reminders", label: "Interview reminders",   desc: "Upcoming scheduled interviews"                },
  { id: "aarya_digest",        label: "Weekly digest",         desc: "Your career progress summary from Aarya"      },
  { id: "profile_views",       label: "Profile viewed",        desc: "When recruiters view your profile"            },
  { id: "application_updates", label: "Application updates",   desc: "Status changes on your applications"          },
  { id: "platform_updates",    label: "Platform updates",      desc: "New Hireloop features and improvements"       },
];

// ── Left-rail nav config ──────────────────────────────────────────────────────

type RailItem = { id: PanelId; label: string; Icon: React.ElementType };

const RAIL_ITEMS: RailItem[] = [
  { id: "home",     label: "Home",     Icon: Home          },
  { id: "inbox",    label: "Intros",   Icon: Inbox         },
  { id: "profile",  label: "Profile",  Icon: User          },
  { id: "jobs",     label: "Matches",  Icon: Briefcase     },
  { id: "coaching", label: "Coaching", Icon: GraduationCap },
];

// ── Shared types ──────────────────────────────────────────────────────────────

// `IntroRequest` is imported from @/lib/api/intros (single source of truth,
// shared with the standalone /intros page and the in-memory cache).

// ── Main component ────────────────────────────────────────────────────────────

interface DashboardClientProps {
  conversationId?: string;
  candidateName?: string;
  initialInput?: string;
  /** Panel to open on first render (e.g. when arriving from /matches). */
  initialPanel?: PanelId;
  /** When true, show the "resume upload or 15-min call" CTA. */
  showUnlockJobsCta?: boolean;
  /** When true, show an Admin button in the top nav (super admin only). */
  showAdminLink?: boolean;
}

export function DashboardClient({
  conversationId: initialConvoId,
  candidateName,
  initialInput,
  initialPanel,
  showUnlockJobsCta = false,
  showAdminLink = false,
}: DashboardClientProps) {
  const router = useRouter();
  const [activeConvoId, setActiveConvoId] = useState<string | null>(
    initialConvoId ?? null
  );
  const [pendingIntros, setPendingIntros] = useState(false);
  const [activePanel, setActivePanel]     = useState<PanelId | null>(initialPanel ?? null);
  const [signingOut, setSigningOut]       = useState(false);
  const [injected, setInjected]           = useState<{ text: string; nonce: number } | null>(null);
  const [savedJobIds, setSavedJobIds]     = useState<Set<string>>(new Set());
  const [savedJobsRefreshKey, setSavedJobsRefreshKey] = useState(0);

  useEffect(() => {
    router.prefetch("/voice");
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

    void fetchMatchFeed(DEFAULT_MATCH_FEED_FILTERS).catch(() => {});
    void fetchMatchFeedCount({ min_score: 0 }).catch(() => {});
    void fetchMyProfile().catch(() => {});
    void fetchIntros().then((rows) => {
      if (!cancelled) {
        setPendingIntros(rows.some((r) => r.status === "pending"));
      }
    }).catch(() => {});

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

  // Send a message into the chat from a side panel (quick action / coaching).
  // Closes the panel so the chat is front-and-centre for the reply.
  function sendToChat(text: string) {
    setActivePanel(null);
    setInjected({ text, nonce: Date.now() });
  }

  // "Request intro" from a job card → close the Jobs panel and pre-fill the
  // chat so Aarya picks up the request with full context.
  function handleRequestIntro(job: MatchedJob) {
    sendToChat(
      `I'd like to request an intro for the "${job.title}" role at ${
        job.company_name ?? "this company"
      } (job ID: ${job.job_id}).`
    );
  }

  // Sign out client-side so we never get caught by <Link> prefetch firing the
  // signout route early. Clear the Supabase session, then hard-redirect.
  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await createClient().auth.signOut();
    } catch {
      // Even if Supabase errors, fall through to the server route which clears
      // the auth cookies and redirects.
    } finally {
      // Full navigation (not router.push) guarantees the session-gated layout
      // re-evaluates against the now-cleared cookies.
      window.location.href = "/login";
    }
  }

  // Poll for pending intro requests (drives inbox notification dot)
  useEffect(() => {
    const check = async () => {
      try {
        const rows = await fetchIntros({ force: true });
        setPendingIntros(rows.some((r) => r.status === "pending"));
      } catch {
        // silent
      }
    };
    const id = window.setInterval(check, 30_000);
    return () => window.clearInterval(id);
  }, []);

  function togglePanel(id: PanelId) {
    setActivePanel((cur) => (cur === id ? null : id));
  }

  return (
    <div className="flex flex-col h-screen bg-paper-0 overflow-hidden">
      {/* ── Top nav ─────────────────────────────────────────────────── */}
      <TopNav
        activePanel={activePanel}
        onTogglePanel={togglePanel}
        pendingIntros={pendingIntros}
        showAdminLink={showAdminLink}
        onSignOut={() => void handleSignOut()}
        signingOut={signingOut}
      />

      {/* Unlock CTA — only shown when no panel is open */}
      {!activePanel && showUnlockJobsCta && (
        <div className="shrink-0 px-4 py-2 border-b border-ink-100">
          <MatchesUnlockGate onUploadResume={() => setActivePanel("profile")} />
        </div>
      )}

      {/* ── Content split: preview LEFT, chat RIGHT ─────────────────── */}
      {/* `relative` anchors the mobile overlay panel below. */}
      <main className="flex-1 min-h-0 flex overflow-hidden relative">
        {/* Preview panel. `key` re-runs the slide-in animation whenever the
            active panel changes.
            - Mobile: full-screen overlay above the chat (no cramped split).
            - Desktop (lg+): fixed left column, clamped 380–600px (~42%). */}
        {activePanel && (
          <div
            key={activePanel}
            className={cn(
              "flex flex-col bg-paper-0 overflow-hidden border-ink-100 animate-slide-in-left",
              "absolute inset-0 z-20 w-full",
              "lg:static lg:inset-auto lg:z-auto lg:w-[clamp(380px,42%,600px)] lg:flex-shrink-0 lg:border-r",
            )}
          >
            {/* Panel header */}
            <div className="flex items-center justify-between h-14 px-5 border-b border-ink-100 shrink-0">
              <h2 className="text-h3 font-semibold text-ink-900">
                {PANEL_TITLE[activePanel]}
              </h2>
              <button
                onClick={() => setActivePanel(null)}
                aria-label="Close panel"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast active:scale-95"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>

            {/* Panel body */}
            <div className="flex-1 overflow-y-auto">
              {activePanel === "home"     && (
                <HomePanel
                  candidateName={candidateName}
                  showUnlockCta={showUnlockJobsCta}
                  onSendToChat={sendToChat}
                  onOpenPanel={setActivePanel}
                />
              )}
              {activePanel === "inbox"    && <InboxPanel />}
              {activePanel === "profile"  && <ProfilePanel onSignOut={() => void handleSignOut()} signingOut={signingOut} />}
              {activePanel === "jobs"     && (
                <JobsPanel
                  conversationId={activeConvoId ?? undefined}
                  locked={showUnlockJobsCta}
                  onRequestIntro={handleRequestIntro}
                  onUnlock={() => setActivePanel("profile")}
                  savedJobIds={savedJobIds}
                  onSavedChange={handleSavedChange}
                  savedJobsRefreshKey={savedJobsRefreshKey}
                />
              )}
              {activePanel === "coaching" && <CoachingPanel onSendToChat={sendToChat} />}
            </div>
          </div>
        )}

        {/* Chat — always visible on the RIGHT; grows to fill when no panel */}
        <div className={cn("overflow-hidden transition-[flex-basis] duration-base ease-out-soft", activePanel ? "flex-1 min-w-0" : "w-full")}>
          <ChatInterface
            conversationId={activeConvoId}
            initialInput={initialInput}
            isLocked={showUnlockJobsCta}
            injectedMessage={injected}
            className="h-full"
            onSessionCreated={(id) => setActiveConvoId(id)}
            savedJobIds={savedJobIds}
            onSavedChange={handleSavedChange}
            onRequestIntro={handleRequestIntro}
          />
        </div>
      </main>
    </div>
  );
}

// ── Home Panel ────────────────────────────────────────────────────────────────

const VISIBILITY_OPTIONS: {
  id: CandidateVisibility;
  label: string;
  hint: string;
  Icon: React.ElementType;
}[] = [
  {
    id: "open_to_matches",
    label: "Open to matches",
    hint: "You'll be shared with companies where Aarya sees a strong fit.",
    Icon: Eye,
  },
  {
    id: "exceptional_only",
    label: "Exceptional only",
    hint: "You'll only be shared for roles that are an exceptional fit.",
    Icon: Sparkles,
  },
  {
    id: "private",
    label: "Don't share",
    hint: "Your profile is never shared automatically. You stay invisible to companies.",
    Icon: EyeOff,
  },
];

/**
 * First-run guidance: a compact "finish setting up" checklist driven by real
 * profile state. Each pending step deep-links to where to complete it; the whole
 * card disappears once profile + résumé + Google are done, so it never nags
 * established users.
 */
function SetupChecklist({
  profile,
  googleConnected,
  jobCount,
  onOpenPanel,
}: {
  profile: MyProfileData | null;
  googleConnected: boolean | null;
  jobCount: number | null;
  onOpenPanel: (id: PanelId) => void;
}) {
  const profileDone = profile?.candidate?.profile_complete === true;
  const resumeDone = !!profile?.resume_filename;
  const googleDone = googleConnected === true;
  const [careerPathDone, setCareerPathDone] = useState(false);

  useEffect(() => {
    if (!profileDone || !resumeDone) return;
    let cancelled = false;
    fetchCareerPath()
      .then((p) => {
        if (!cancelled) {
          setCareerPathDone(Boolean(p?.steps?.length || p?.target_titles?.length));
        }
      })
      .catch(() => {
        if (!cancelled) setCareerPathDone(false);
      });
    return () => {
      cancelled = true;
    };
  }, [profileDone, resumeDone]);

  const steps = [
    {
      id: "profile",
      label: "Complete your profile",
      hint: "Add your title, experience, skills & expectations.",
      done: profileDone,
      cta: "Complete",
    },
    {
      id: "resume",
      label: "Add your résumé",
      hint: "Aarya auto-fills your profile straight from it.",
      done: resumeDone,
      cta: "Upload",
    },
    {
      id: "paths",
      label: "Review career paths",
      hint: "Pick a direction before Aarya searches roles.",
      done: careerPathDone,
      cta: "View paths",
      panel: "jobs" as PanelId,
    },
    {
      id: "google",
      label: "Connect Google (optional)",
      hint: "Send intros from your Gmail and get Meet links on calls.",
      done: googleDone,
      cta: "Connect",
    },
  ];

  // Don't render until we actually know the state, and hide once all done.
  if (profile === null) return null;
  if (steps.every((s) => s.done)) return null;

  const doneCount = steps.filter((s) => s.done).length;
  const essentialsDone = profileDone && resumeDone && careerPathDone;

  return (
    <FadeUp>
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.5} />
            <p className="text-small font-semibold text-ink-900">Finish setting up</p>
          </div>
          <span className="text-micro text-ink-500">{doneCount}/{steps.length} done</span>
        </div>

        <ul className="space-y-1.5">
          {steps.map((s) => (
            <li key={s.id} className="flex items-center gap-3">
              {s.done ? (
                <Check className="h-4 w-4 text-ink-900 shrink-0" strokeWidth={2} />
              ) : (
                <Circle className="h-4 w-4 text-ink-300 shrink-0" strokeWidth={1.5} />
              )}
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "text-small",
                    s.done ? "text-ink-400 line-through" : "text-ink-800 font-medium"
                  )}
                >
                  {s.label}
                </p>
                {!s.done && <p className="text-micro text-ink-500">{s.hint}</p>}
              </div>
              {!s.done && (
                <button
                  type="button"
                  onClick={() =>
                    onOpenPanel(
                      "panel" in s && s.panel ? s.panel : "profile"
                    )
                  }
                  className="shrink-0 inline-flex items-center rounded-full border border-ink-200 bg-paper-0 px-3 py-1 text-micro font-medium text-ink-700 hover:border-ink-300 hover:bg-ink-50 transition-colors"
                >
                  {s.cta}
                </button>
              )}
            </li>
          ))}
        </ul>

        {essentialsDone && jobCount != null && jobCount > 0 && (
          <button
            type="button"
            onClick={() => onOpenPanel("jobs")}
            className="w-full inline-flex items-center justify-center gap-1.5 rounded-md bg-ink-900 px-3 py-2 text-small font-medium text-paper-0 hover:bg-ink-800 transition-colors"
          >
            <Search className="h-4 w-4" strokeWidth={1.5} />
            See your {jobCount} {jobCount === 1 ? "match" : "matches"}
          </button>
        )}
      </CardBody>
    </Card>
    </FadeUp>
  );
}

function HomePanel({
  candidateName,
  showUnlockCta,
  onSendToChat,
  onOpenPanel,
}: {
  candidateName?: string;
  showUnlockCta?: boolean;
  onSendToChat: (text: string) => void;
  onOpenPanel: (id: PanelId) => void;
}) {
  const { toast } = useToast();
  const firstName = candidateName?.split(" ")[0] ?? "there";

  const activeIntroCount = (rows: IntroRequest[]) =>
    rows.filter((r) => !["declined", "expired", "cancelled"].includes(r.status)).length;

  const [jobCount, setJobCount]       = useState<number | null>(
    () => getCachedMatchFeedCount({ min_score: 0 })
  );
  const [introCount, setIntroCount]   = useState<number | null>(() => {
    const cached = getCachedIntros();
    return cached ? activeIntroCount(cached) : null;
  });
  const [visibility, setVisibility]   = useState<CandidateVisibility | null>(
    () => getCachedProfile()?.candidate?.visibility ?? null
  );
  const [savingVis, setSavingVis]     = useState<CandidateVisibility | null>(null);
  const [profileData, setProfileData] = useState<MyProfileData | null>(() => getCachedProfile());
  const [googleConnected, setGoogleConnected] = useState<boolean | null>(null);
  const [hasCareerPath, setHasCareerPath] = useState(false);
  const [intelArchetype, setIntelArchetype] = useState<string | null>(null);
  const [intelNextRole, setIntelNextRole] = useState<string | null>(null);
  const [intelCompleteness, setIntelCompleteness] = useState<number | null>(null);

  useEffect(() => {
    fetchMatchFeedCount({ min_score: 0 })
      .then((total) => setJobCount(total))
      .catch(() => setJobCount(0));

    fetchIntros()
      .then((rows) => setIntroCount(activeIntroCount(rows)))
      .catch(() => setIntroCount(0));

    fetchMyProfile()
      .then((d) => {
        setProfileData(d);
        setVisibility(d.candidate?.visibility ?? "open_to_matches");
      })
      .catch(() => setVisibility("open_to_matches"));

    fetchGoogleStatus()
      .then((s) => setGoogleConnected(s.connected))
      .catch(() => setGoogleConnected(null)); // unknown → treated as not-yet-done, non-blocking

    fetchCareerPath()
      .then((p) => setHasCareerPath(Boolean(p?.steps?.length || p?.target_titles?.length)))
      .catch(() => setHasCareerPath(false));

    fetchCareerIntelligence()
      .then((intel) => {
        if (!intel) return;
        setIntelArchetype(intel.career_dna?.primary_archetype ?? null);
        setIntelNextRole(intel.prediction?.most_likely_next_role?.outcome ?? null);
        setIntelCompleteness(intel.data_completeness ?? null);
      })
      .catch(() => {});
  }, []);

  async function selectVisibility(next: CandidateVisibility) {
    if (next === visibility || savingVis) return;
    const prev = visibility;
    setVisibility(next);
    setSavingVis(next);
    try {
      await updateProfileVisibility(next);
      invalidateProfileCache();
      toast.success("Visibility updated");
    } catch {
      setVisibility(prev);
      toast.error("Couldn't update visibility");
    } finally {
      setSavingVis(null);
    }
  }

  const QUICK_ACTIONS: {
    label: string;
    Icon: React.ElementType;
    onClick: () => void;
  }[] = [
    { label: "See my matches",       Icon: Briefcase,          onClick: () => onOpenPanel("jobs") },
    { label: "Plan career paths",    Icon: Search,             onClick: () => onSendToChat("Show me my top 3 career paths and help me pick one to prioritize.") },
    { label: "Update preferences",   Icon: SlidersHorizontal,  onClick: () => onSendToChat("I'd like to update my job preferences.") },
    { label: "Salary expectations",  Icon: IndianRupee,        onClick: () => onSendToChat("Based on my profile, what could I earn in my next role?") },
    { label: "Improve my CV",        Icon: FileText,           onClick: () => onSendToChat("Can you help me improve my CV?") },
  ];

  const profileReady =
    profileData?.candidate?.profile_complete === true &&
    Boolean(profileData?.resume_filename);

  const activeVis = VISIBILITY_OPTIONS.find((o) => o.id === visibility);

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      {/* Welcome */}
      <div>
        <h3 className="text-h2 font-semibold text-ink-900">Welcome back, {firstName}</h3>
        <p className="text-small text-ink-500 mt-0.5">
          Chat with Aarya on the right — use panels here for matches, profile, and intros.
        </p>
      </div>

      <NextBestStep
        profile={profileData}
        hasCareerPath={hasCareerPath}
        matchCount={jobCount}
      />

      <IntelligenceHero
        archetype={intelArchetype}
        nextRole={intelNextRole}
        completeness={intelCompleteness}
        onOpenIntelligence={() => onOpenPanel("profile")}
        onAskAarya={onSendToChat}
      />

      {/* First-run guidance — what to do next, hidden once setup is complete */}
      <SetupChecklist
        profile={profileData}
        googleConnected={googleConnected}
        jobCount={jobCount}
        onOpenPanel={onOpenPanel}
      />

      {profileReady && !hasCareerPath && (
        <CareerPathOptionCards
          onSelectPath={(opt) => {
            onSendToChat(
              `I want to prioritize the "${opt.title}" career path. Show me matching jobs for this direction.`
            );
          }}
          onPathsReady={(n) => {
            if (n > 0) setHasCareerPath(true);
          }}
        />
      )}

      {/* Quick action chips */}
      <div className="flex flex-wrap gap-2">
        {QUICK_ACTIONS.map(({ label, Icon, onClick }) => (
          <Button
            key={label}
            variant="secondary"
            size="sm"
            onClick={onClick}
            leftIcon={<Icon className="h-4 w-4 text-ink-500" strokeWidth={1.5} />}
          >
            {label}
          </Button>
        ))}
      </div>

      {/* Unlock CTA (when locked) */}
      {showUnlockCta && (
        <Card>
          <CardBody className="space-y-2.5">
            <div className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-accent" strokeWidth={1.5} />
              <p className="text-small font-semibold text-ink-900">Unlock job matches</p>
            </div>
            <p className="text-micro text-ink-600">
              Upload your resume or start a 15‑min voice session with Aarya.
              Either path unlocks personalised matches.
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onOpenPanel("profile")}
              >
                Upload resume
              </Button>
              <Link
                href="/voice"
                className={cn(
                  "inline-flex items-center justify-center font-medium",
                  "transition-colors duration-fast ease-out-soft",
                  "bg-accent text-accent-fg hover:bg-accent-hover",
                  "h-8 px-3 text-small gap-1.5 rounded-md"
                )}
              >
                <Phone className="h-3.5 w-3.5" strokeWidth={2} />
                15‑min call
              </Link>
            </div>
          </CardBody>
        </Card>
      )}

      {/* Talk to Aarya */}
      <Card>
        <CardBody className="space-y-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-ink-900 flex items-center justify-center shrink-0">
              <Phone className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
            </div>
            <div>
              <p className="text-small font-semibold text-ink-900">Talk to Aarya</p>
              <p className="text-micro text-ink-500">Voice conversation</p>
            </div>
          </div>
          <p className="text-micro text-ink-600">
            Start a voice conversation to discuss jobs, update your preferences,
            or get help with your job search.
          </p>
          <Link
            href="/voice"
            className={cn(
              "inline-flex items-center justify-center font-medium",
              "transition-colors duration-fast ease-out-soft",
              "bg-accent text-accent-fg hover:bg-accent-hover",
              "h-10 px-4 text-body gap-2 rounded-md"
            )}
          >
            <Phone className="h-3.5 w-3.5" strokeWidth={2} />
            Start call
          </Link>
        </CardBody>
      </Card>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3">
        <StatCard
          title="Matches"
          subtitle="Roles ranked for your profile"
          count={jobCount}
          unit="jobs"
          actionLabel="View matches"
          onAction={() => onOpenPanel("jobs")}
        />
        <StatCard
          title="Intros"
          subtitle="Active intro requests"
          count={introCount}
          unit="open"
          actionLabel="View intros"
          onAction={() => onOpenPanel("inbox")}
        />
      </div>

      {/* Profile visibility */}
      <Card>
        <CardHeader
          title="Profile Visibility"
          description="Control how your profile is shared with companies"
        />
        <CardBody className="!pt-0 space-y-2">
          {VISIBILITY_OPTIONS.map((opt) => {
            const isActive = visibility === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => void selectVisibility(opt.id)}
                disabled={savingVis !== null}
                className={cn(
                  "w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-fast",
                  isActive
                    ? "border-ink-900 bg-ink-50"
                    : "border-ink-200 hover:border-ink-300 hover:bg-ink-50",
                  savingVis !== null && "opacity-70"
                )}
              >
                <opt.Icon
                  className={cn("h-4 w-4 shrink-0", isActive ? "text-ink-900" : "text-ink-400")}
                  strokeWidth={1.5}
                />
                <span className={cn("text-small font-medium flex-1", isActive ? "text-ink-900" : "text-ink-700")}>
                  {opt.label}
                </span>
                {savingVis === opt.id ? (
                  <Loader2 className="h-4 w-4 text-ink-400 animate-spin" strokeWidth={1.5} />
                ) : (
                  isActive && (
                    <span className="w-2 h-2 rounded-full bg-accent" />
                  )
                )}
              </button>
            );
          })}
          {activeVis && (
            <p className="text-micro text-ink-500 pt-1">{activeVis.hint}</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  title,
  subtitle,
  count,
  unit,
  actionLabel,
  onAction,
}: {
  title: string;
  subtitle: string;
  count: number | null;
  unit: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <Card className="flex flex-col">
      <CardBody className="flex-1 space-y-1">
        <p className="text-small font-semibold text-ink-900">{title}</p>
        <p className="text-micro text-ink-500">{subtitle}</p>
        <div className="flex items-baseline gap-1.5 pt-1">
          {count === null ? (
            <Loader2 className="h-5 w-5 text-ink-300 animate-spin" strokeWidth={1.5} />
          ) : (
            <span className="text-h1 font-semibold text-ink-900 leading-none">{count}</span>
          )}
          <span className="text-micro text-ink-400">{unit}</span>
        </div>
      </CardBody>
      <CardFooter>
        <button
          onClick={onAction}
          className="inline-flex items-center gap-1 text-small font-medium text-ink-700 hover:text-ink-900 transition-colors"
        >
          {actionLabel}
          <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
        </button>
      </CardFooter>
    </Card>
  );
}

// ── Inbox Panel ───────────────────────────────────────────────────────────────

const INTRO_STATUS: Record<
  string,
  { label: string; tone: "muted" | "strong" | "accent" }
> = {
  pending:            { label: "Pending",       tone: "muted"  },
  recruiter_notified: { label: "Notified",      tone: "accent" },
  draft_ready:        { label: "Email drafted", tone: "accent" },
  sent:               { label: "Intro sent ✓", tone: "strong" },
  declined:           { label: "Declined",      tone: "muted"  },
  expired:            { label: "Expired",       tone: "muted"  },
  cancelled:          { label: "Cancelled",     tone: "muted"  },
};

function InboxPanel() {
  const { toast } = useToast();
  // Paint cached intros instantly on reopen (the panel remounts each time),
  // then revalidate in the background — same pattern as the Profile panel.
  const cached = getCachedIntros();
  const [intros, setIntros]         = useState<IntroRequest[]>(cached ?? []);
  const [loading, setLoading]       = useState(cached === null);
  const [cancelling, setCancelling] = useState<string | null>(null);

  useEffect(() => {
    fetchIntros()
      .then(setIntros)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function cancel(id: string) {
    setCancelling(id);
    try {
      await cancelIntro(id);
      setIntros((prev) =>
        prev.map((i) => (i.id === id ? { ...i, status: "cancelled" } : i))
      );
      toast.success("Intro request cancelled");
    } catch (e) {
      // Surface the failure — previously the click silently did nothing, leaving
      // the user unsure whether it worked.
      toast.error(e instanceof Error ? e.message : "Couldn't cancel — please try again");
    } finally {
      setCancelling(null);
    }
  }

  function timeAgo(iso: string) {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (d === 0) return "Today";
    if (d === 1) return "Yesterday";
    return `${d}d ago`;
  }

  if (loading) {
    return (
      <div className="p-5 space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 rounded-lg bg-ink-100 animate-skeleton" />
        ))}
      </div>
    );
  }

  if (intros.length === 0) {
    return (
      <div className="p-5">
        <EmptyState
          icon={<Building2 strokeWidth={1.5} />}
          title="No intro requests yet"
          description="Ask Aarya to request an intro for any job match. She'll draft a warm email to the hiring manager via your Gmail."
          action={
            <Link href="/dashboard">
              <Button
                variant="primary"
                size="sm"
                leftIcon={<MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />}
              >
                Ask Aarya
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="p-5 space-y-3">
      {intros.map((intro) => {
        const meta = INTRO_STATUS[intro.status] ?? {
          label: intro.status,
          tone: "muted" as const,
        };
        const canCancel = ["pending", "recruiter_notified"].includes(intro.status);

        return (
          <Card
            key={intro.id}
            className={cn(
              "transition-opacity",
              ["cancelled", "expired"].includes(intro.status) && "opacity-60"
            )}
          >
            <CardBody>
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-md bg-ink-100 flex items-center justify-center shrink-0 mt-0.5">
                  <Building2 className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 mb-0.5">
                    <p className="text-small font-medium text-ink-900 truncate">
                      {intro.job_title}
                    </p>
                    <Badge tone={meta.tone} className="shrink-0 text-[10px]">
                      {meta.label}
                    </Badge>
                  </div>
                  {intro.company_name && (
                    <p className="text-micro text-ink-500 truncate">
                      {intro.company_name}
                      {intro.hm_name && ` · ${intro.hm_name}`}
                    </p>
                  )}
                  {intro.replied_at && (
                    <p className="text-micro text-accent font-medium mt-1">
                      Replied {timeAgo(intro.replied_at)}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-micro text-ink-300">
                      {timeAgo(intro.created_at)}
                    </span>
                    {canCancel && (
                      <button
                        onClick={() => void cancel(intro.id)}
                        disabled={cancelling === intro.id}
                        className="text-micro text-ink-400 hover:text-ink-900 transition-colors disabled:opacity-40"
                      >
                        {cancelling === intro.id ? "Cancelling…" : "Cancel"}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
        );
      })}
    </div>
  );
}

// ── Profile Panel ─────────────────────────────────────────────────────────────

/**
 * Skeleton shown while the profile loads — static ink-50 pulse, no spinner,
 * mirroring the Overview form's shape so the layout doesn't jump on load.
 * (DESIGN.md §8: loading states use skeleton blocks, not spinners.)
 */
function ProfileSkeleton() {
  return (
    <div className="animate-skeleton space-y-4" aria-hidden="true">
      <Card>
        <CardBody className="space-y-4">
          <div className="h-4 w-32 rounded bg-ink-100" />
          <div className="h-9 w-full rounded bg-ink-100" />
          <div className="h-20 w-full rounded bg-ink-100" />
          <div className="grid grid-cols-2 gap-3">
            <div className="h-9 rounded bg-ink-100" />
            <div className="h-9 rounded bg-ink-100" />
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            <div className="h-5 w-16 rounded-full bg-ink-100" />
            <div className="h-5 w-20 rounded-full bg-ink-100" />
            <div className="h-5 w-14 rounded-full bg-ink-100" />
            <div className="h-5 w-24 rounded-full bg-ink-100" />
          </div>
        </CardBody>
      </Card>
      <Card>
        <CardBody className="space-y-3">
          <div className="h-4 w-40 rounded bg-ink-100" />
          <div className="h-16 w-full rounded bg-ink-100" />
        </CardBody>
      </Card>
    </div>
  );
}

type ProfileTab = "overview" | "experience" | "intelligence" | "settings";

function ProfilePanel({
  onSignOut,
  signingOut,
}: {
  onSignOut: () => void;
  signingOut: boolean;
}) {
  const { toast } = useToast();

  const [tab,            setTab]            = useState<ProfileTab>("overview");
  const [profile,        setProfile]        = useState<MyProfileData | null>(null);
  const [experience,     setExperience]     = useState<WorkExperience[]>([]);
  const [education,      setEducation]      = useState<Education[]>([]);
  const [prefs,          setPrefs]          = useState<Record<string, Record<string, boolean>>>({});

  const [fullName,       setFullName]       = useState("");
  const [headline,       setHeadline]       = useState("");
  const [currentTitle,   setCurrentTitle]   = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [summary,        setSummary]        = useState("");
  const [lookingFor,     setLookingFor]     = useState("");

  // Start unblocked if we already have a cached profile from a previous open —
  // the panel remounts each time it's reopened, so the cache makes it instant.
  const [loadingProfile, setLoadingProfile] = useState(() => getCachedProfile() === null);
  const [profileError,   setProfileError]   = useState("");
  const [savingProfile,  setSavingProfile]  = useState(false);
  const [savingPrefs,    setSavingPrefs]    = useState(false);
  const [remotePref,     setRemotePref]     = useState<RemotePreference>("any");
  const [savingRemote,   setSavingRemote]   = useState<RemotePreference | null>(null);

  function hydrate(d: MyProfileData) {
    applyProfileToForm(d, {
      setProfile,
      setFullName,
      setHeadline,
      setCurrentTitle,
      setSummary,
      setCurrentCompany,
      setLookingFor,
    });
    const pref = d.candidate?.remote_preference;
    if (pref === "any" || pref === "remote_only" || pref === "onsite_only") {
      setRemotePref(pref);
    } else {
      setRemotePref("any");
    }
    setExperience(d.experience ?? []);
    setEducation(d.education ?? []);
  }

  async function selectRemotePreference(next: RemotePreference) {
    if (next === remotePref || savingRemote) return;
    const prev = remotePref;
    setRemotePref(next);
    setSavingRemote(next);
    try {
      await updateRemotePreference(next);
      invalidateProfileCache();
      toast.success("Job search filter updated");
    } catch {
      setRemotePref(prev);
      toast.error("Couldn't update job filter");
    } finally {
      setSavingRemote(null);
    }
  }

  useEffect(() => {
    const loadProfile = async () => {
      // Paint cached data immediately (no spinner); still revalidate below.
      const cached = getCachedProfile();
      if (cached) {
        hydrate(cached);
        setLoadingProfile(false);
      } else {
        setLoadingProfile(true);
      }
      setProfileError("");
      try {
        hydrate(await fetchMyProfile());
      } catch (err) {
        const supabase = createClient();
        const { data: { user } } = await supabase.auth.getUser();
        if (user) {
          const meta = user.user_metadata as Record<string, unknown> | undefined;
          const name =
            (typeof meta?.full_name === "string" && meta.full_name) ||
            (typeof meta?.name === "string" && meta.name) ||
            "";
          setFullName(name);
          setProfile({
            user: { id: user.id, email: user.email ?? "", phone: null, full_name: name || null },
            candidate: null,
          });
        }
        setProfileError(
          err instanceof Error
            ? err.message
            : "Couldn't load profile. Check that the API is running."
        );
      } finally {
        setLoadingProfile(false);
      }
    };

    void loadProfile();

    apiFetch<{ prefs: Record<string, Record<string, boolean>> }>(
      "/api/v1/me/notification-prefs"
    )
      .then((d) => setPrefs(d.prefs ?? {}))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (tab !== "experience" && tab !== "intelligence") return;
    void fetchMyProfile({ force: true })
      .then(hydrate)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function handleSaveProfile() {
    setSavingProfile(true);
    try {
      await apiFetch("/api/v1/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name:       fullName.trim() || undefined,
          headline:        headline.trim() || undefined,
          current_title:   currentTitle.trim() || undefined,
          current_company: currentCompany.trim() || undefined,
          summary:         summary.trim() || undefined,
          looking_for:     lookingFor.trim() || undefined,
        }),
      });
      hydrate(await fetchMyProfile({ force: true }));
      setProfileError("");
      toast.success("Profile updated");
    } catch {
      toast.error("Couldn't update profile");
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleSavePrefs() {
    setSavingPrefs(true);
    try {
      await apiFetch("/api/v1/me/notification-prefs", {
        method: "PATCH",
        body: JSON.stringify({ prefs }),
      });
      toast.success("Notification preferences saved");
    } catch {
      toast.error("Couldn't save preferences");
    } finally {
      setSavingPrefs(false);
    }
  }

  function setToggle(catId: string, checked: boolean) {
    setPrefs((p) => ({ ...p, [catId]: { ...(p[catId] ?? {}), whatsapp: checked } }));
  }

  const inputClass =
    "w-full px-3 py-2 rounded-md border border-ink-200 bg-paper-0 text-small text-ink-900 " +
    "placeholder:text-ink-400 focus:outline-none focus:ring-1 focus:ring-ink-900 transition-shadow";

  const name      = fullName || profile?.user?.full_name || "Your profile";
  const initials  = name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "U";
  const isActive  = profile?.candidate?.is_active !== false;
  const linkedinUrl =
    (profile?.candidate as { linkedin_url?: string } | null | undefined)?.linkedin_url ?? null;

  const TABS: { id: ProfileTab; label: string }[] = [
    { id: "overview",     label: "Overview"     },
    { id: "experience",   label: "Experience"   },
    { id: "intelligence", label: "Intelligence" },
    { id: "settings",     label: "Settings"     },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-start gap-3">
          {profile?.user?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.user.avatar_url}
              alt={name}
              className="w-14 h-14 rounded-full object-cover shrink-0"
            />
          ) : (
            <div className="w-14 h-14 rounded-full bg-ink-900 flex items-center justify-center shrink-0">
              <span className="text-paper-0 text-h3 font-semibold">{initials}</span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-h3 font-semibold text-ink-900 truncate">{name}</h3>
              {isActive && (
                <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-micro font-medium text-accent">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  Actively Looking
                </span>
              )}
            </div>
            <p className="text-small text-ink-500 truncate mt-0.5">
              {headline || "Add a headline to stand out"}
            </p>
            <div className="flex items-center gap-2 mt-2">
              {linkedinUrl && (
                <a
                  href={linkedinUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-ink-200 px-2.5 py-1.5 text-micro font-medium text-ink-700 hover:bg-ink-50 transition-colors"
                >
                  <Linkedin className="h-3.5 w-3.5" strokeWidth={1.5} />
                  View LinkedIn
                </a>
              )}
              <button
                type="button"
                onClick={() => setTab("overview")}
                className="inline-flex items-center gap-1.5 rounded-md border border-ink-200 px-2.5 py-1.5 text-micro font-medium text-ink-700 hover:bg-ink-50 transition-colors"
              >
                <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
                Update CV
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 px-5 border-b border-ink-100">
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
                active ? "border-ink-900 text-ink-900" : "border-transparent text-ink-400 hover:text-ink-700"
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ── Tab body ────────────────────────────────────────────────────── */}
      <div key={tab} className="flex-1 overflow-y-auto p-5 space-y-4 animate-fade-in">
        {loadingProfile && <ProfileSkeleton />}
        {profileError && <p className="text-small text-ink-700">{profileError}</p>}

        {/* ── OVERVIEW ─────────────────────────────────────────────────── */}
        {tab === "overview" && !loadingProfile && (
          <>
            <Card>
              <CardHeader title="Overview" description={profile?.user?.email ?? undefined} />
              <CardBody className="space-y-3 !pt-0">
                <Field label="Headline">
                  <input className={inputClass} value={headline}
                    onChange={(e) => setHeadline(e.target.value)}
                    placeholder="e.g. Senior Software Engineer" />
                </Field>
                <Field label="Summary">
                  <textarea className={cn(inputClass, "min-h-[88px] resize-y")} value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                    placeholder="A short bio or career summary" />
                </Field>
                <Field label="What I'm looking for">
                  <textarea className={cn(inputClass, "min-h-[72px] resize-y")} value={lookingFor}
                    onChange={(e) => setLookingFor(e.target.value)}
                    placeholder="The kind of role / opportunity you want next" />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Current role">
                    <input className={inputClass} value={currentTitle}
                      onChange={(e) => setCurrentTitle(e.target.value)} placeholder="e.g. Sales Lead" />
                  </Field>
                  <Field label="Company">
                    <input className={inputClass} value={currentCompany}
                      onChange={(e) => setCurrentCompany(e.target.value)} placeholder="e.g. Hireloop" />
                  </Field>
                </div>

                {profile?.candidate?.skills && profile.candidate.skills.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">Skills</span>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.candidate.skills.slice(0, 14).map((s) => (
                        <span key={s} className="px-2 py-0.5 rounded-full bg-ink-100 text-micro text-ink-700 font-medium">
                          {s}
                        </span>
                      ))}
                      {profile.candidate.skills.length > 14 && (
                        <span className="px-2 py-0.5 rounded-full bg-ink-100 text-micro text-ink-500">
                          +{profile.candidate.skills.length - 14} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </CardBody>
              <CardFooter>
                <Button variant="primary" size="sm" onClick={() => void handleSaveProfile()} loading={savingProfile}>
                  Save profile
                </Button>
              </CardFooter>
            </Card>

            {/* Re-upload CV → re-parse → auto-fill profile */}
            <Card>
              <CardHeader
                title="Resume / CV"
                description="Upload a new CV and Aarya will re-extract your details and update your profile."
              />
              <CardBody className="!pt-0">
                <ResumeUpload
                  autoApply
                  currentFileName={profile?.resume_filename ?? null}
                  onDone={async (_id, parsed) => {
                    try {
                      hydrate(await fetchMyProfile());
                      setProfileError("");
                    } catch {
                      /* keep the parsed preview even if re-fetch fails */
                    }
                    const count = parsed.skills?.length ?? 0;
                    toast.success(
                      count
                        ? `Profile updated from your CV — ${count} skills detected`
                        : "Profile updated from your CV"
                    );
                  }}
                />
              </CardBody>
            </Card>

            {/* Connect Google → send intros from own Gmail (P13) + Calendar/Meet on booking (P07) */}
            <GoogleConnectCard />
          </>
        )}

        {/* ── EXPERIENCE ───────────────────────────────────────────────── */}
        {tab === "experience" && !loadingProfile && (
          <>
            <Card>
              <CardHeader
                title="Experience"
                description="Merged from LinkedIn, your CV, and Aarya’s analysis of each role."
              />
              <CardBody className="!pt-0">
                {experience.length === 0 ? (
                  <EmptyState
                    icon={<Briefcase strokeWidth={1.5} />}
                    title="No experience yet"
                    description="Connect LinkedIn or upload your CV in Overview — Aarya will fill this in with her take on each role."
                  />
                ) : (
                  <ol className="relative space-y-0">
                    {experience.map((exp, i) => (
                      <ExperienceItem key={`${exp.company}-${i}`} exp={exp} last={i === experience.length - 1} />
                    ))}
                  </ol>
                )}
              </CardBody>
            </Card>

            {education.length > 0 && (
              <Card>
                <CardHeader title="Education" />
                <CardBody className="!pt-0 space-y-3">
                  {education.map((ed, i) => (
                    <div key={`${ed.institution}-${i}`} className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-md bg-ink-100 flex items-center justify-center shrink-0 mt-0.5">
                        <GraduationCap className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-small font-medium text-ink-900">{ed.institution ?? "—"}</p>
                        <p className="text-micro text-ink-500">
                          {[ed.degree, ed.field_of_study].filter(Boolean).join(" · ") || "—"}
                        </p>
                        {(ed.start_date || ed.end_date) && (
                          <p className="text-micro text-ink-400">
                            {[ed.start_date, ed.end_date].filter(Boolean).join(" – ")}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}
          </>
        )}

        {/* ── INTELLIGENCE ─────────────────────────────────────────────── */}
        {tab === "intelligence" && <CareerIntelligencePanel />}

        {/* ── SETTINGS ─────────────────────────────────────────────────── */}
        {tab === "settings" && (
          <>
            {profile?.user?.phone && (
              <Card>
                <CardBody className="!py-3">
                  <p className="text-small text-ink-600">
                    Phone: <span className="text-ink-900">{profile.user.phone}</span>
                  </p>
                </CardBody>
              </Card>
            )}

            <Card>
              <CardHeader
                title="Job search"
                description="Filter matches in Jobs and when Aarya searches for you. You can also change this in chat."
              />
              <CardBody className="!pt-0 space-y-2">
                {REMOTE_PREFERENCE_OPTIONS.map((opt) => {
                  const isActive = remotePref === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => void selectRemotePreference(opt.id)}
                      disabled={savingRemote !== null}
                      className={cn(
                        "w-full flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-fast",
                        isActive
                          ? "border-ink-900 bg-ink-50"
                          : "border-ink-200 hover:border-ink-300 hover:bg-ink-50",
                        savingRemote !== null && "opacity-70"
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <p
                          className={cn(
                            "text-small font-medium",
                            isActive ? "text-ink-900" : "text-ink-700"
                          )}
                        >
                          {opt.label}
                        </p>
                        <p className="text-micro text-ink-500 mt-0.5">{opt.hint}</p>
                      </div>
                      {savingRemote === opt.id ? (
                        <Loader2
                          className="h-4 w-4 text-ink-400 animate-spin shrink-0 mt-0.5"
                          strokeWidth={1.5}
                        />
                      ) : (
                        isActive && (
                          <span className="w-2 h-2 rounded-full bg-accent shrink-0 mt-1.5" />
                        )
                      )}
                    </button>
                  );
                })}
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="Notifications" description="Choose how Aarya keeps you updated." />
              <CardBody className="!pt-0 space-y-0.5">
                {NOTIFICATION_CATEGORIES.map((cat) => (
                  <div key={cat.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="text-small font-medium text-ink-900">{cat.label}</p>
                      <p className="text-micro text-ink-500 truncate">{cat.desc}</p>
                    </div>
                    <Toggle checked={prefs[cat.id]?.whatsapp ?? true} onChange={(v) => setToggle(cat.id, v)} />
                  </div>
                ))}
              </CardBody>
              <CardFooter>
                <Button variant="primary" size="sm" onClick={() => void handleSavePrefs()} loading={savingPrefs}>
                  Save preferences
                </Button>
              </CardFooter>
            </Card>

            <Card>
              <CardHeader title="Privacy & account" description="DPDP Act 2023 compliant." />
              <CardBody className="!pt-0 space-y-2">
                <button
                  onClick={() =>
                    window.open(
                      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/me/dpdp/export`,
                      "_blank"
                    )
                  }
                  className="w-full flex items-center gap-2.5 rounded-md border border-ink-200 px-3 py-2.5 text-small text-ink-700 hover:bg-ink-50 transition-colors text-left"
                >
                  <Shield className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
                  Export my data (JSON)
                </button>
                <button
                  onClick={onSignOut}
                  disabled={signingOut}
                  className="w-full flex items-center gap-2.5 rounded-md border border-ink-200 px-3 py-2.5 text-small text-ink-700 hover:bg-ink-50 transition-colors text-left disabled:opacity-50"
                >
                  <LogOut className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
                  {signingOut ? "Signing out…" : "Sign out"}
                </button>
                <p className="text-micro text-ink-400 pt-1">DPO: privacy@hireloop.in</p>
              </CardBody>
            </Card>

            {/* Admin entry — only for DB admins or founders in SUPER_ADMIN_EMAILS */}
            {profile?.user?.is_admin && (
              <Card>
                <CardHeader title="Admin" description="Internal — user management, bias audit & observability." />
                <CardBody className="!pt-0">
                  <a
                    href="/admin"
                    className="w-full flex items-center gap-2.5 rounded-md border border-ink-200 px-3 py-2.5 text-small text-ink-700 hover:bg-ink-50 transition-colors text-left"
                  >
                    <Shield className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
                    Open admin panel
                  </a>
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Profile helpers ─────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">{label}</span>
      {children}
    </label>
  );
}

function ExperienceItem({
  exp,
  last,
}: {
  exp: WorkExperience;
  last: boolean;
}) {
  const dates = [exp.start_date, exp.is_current ? "Present" : exp.end_date]
    .filter(Boolean)
    .join(" – ");
  const meta = [exp.location, exp.industry, exp.employment_type, exp.seniority]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="relative flex gap-3 pb-4">
      <div className="flex flex-col items-center">
        <div className="w-9 h-9 rounded-md bg-ink-100 flex items-center justify-center shrink-0">
          <Building2 className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
        </div>
        {!last && <span className="w-px flex-1 bg-ink-100 mt-1" />}
      </div>
      <div className="min-w-0 pb-1 space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-small font-semibold text-ink-900">{exp.title ?? "—"}</p>
            {exp.company && <p className="text-micro text-ink-600">{exp.company}</p>}
          </div>
          {exp.source === "linkedin" && (
            <Badge className="shrink-0">LinkedIn</Badge>
          )}
        </div>
        {meta && <p className="text-micro text-ink-500">{meta}</p>}
        {dates && (
          <p className="text-micro text-ink-400 flex items-center gap-1">
            <MapPin className="h-3 w-3" strokeWidth={1.5} />
            {dates}
          </p>
        )}
        {exp.description && (
          <p className="text-micro text-ink-500 leading-snug">{exp.description}</p>
        )}
        {exp.aarya_insights && exp.aarya_insights.length > 0 && (
          <div className="rounded-md bg-ink-50 border border-ink-100 px-3 py-2 mt-1">
            <p className="text-micro font-medium text-ink-700 mb-1">Aarya&apos;s take</p>
            <ul className="list-disc pl-4 space-y-0.5">
              {exp.aarya_insights.map((line, idx) => (
                <li key={idx} className="text-micro text-ink-600 leading-snug">
                  {line}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}

// ── Jobs Panel ────────────────────────────────────────────────────────────────

type JobsTab = "matches" | "path" | "saved";

function JobsPanel({
  conversationId,
  locked,
  onRequestIntro,
  onUnlock,
  savedJobIds,
  onSavedChange,
  savedJobsRefreshKey,
}: {
  conversationId?: string;
  locked?: boolean;
  onRequestIntro: (job: MatchedJob) => void;
  onUnlock: () => void;
  savedJobIds: Set<string>;
  onSavedChange: (jobId: string, saved: boolean) => void;
  savedJobsRefreshKey: number;
}) {
  const [tab, setTab] = useState<JobsTab>("matches");
  // Locked users have no matches yet — show the unlock paths instead of an
  // empty feed, mirroring the dashboard's unlock CTA.
  if (locked) {
    return (
      <div className="p-5 space-y-4">
        <Card>
          <CardBody>
            <div className="flex flex-col items-center gap-4 py-6 text-center">
              <div className="w-14 h-14 rounded-xl bg-ink-100 flex items-center justify-center">
                <Briefcase className="h-7 w-7 text-ink-500" strokeWidth={1.5} />
              </div>
              <div className="space-y-1">
                <p className="text-small font-semibold text-ink-900">
                  Unlock your job matches
                </p>
                <p className="text-micro text-ink-500 max-w-xs">
                  Upload your resume or do a 15‑min call with Aarya — either
                  path unlocks personalised matches.
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-2">
                <button
                  type="button"
                  onClick={onUnlock}
                  className="inline-flex items-center gap-1.5 rounded-full border border-ink-200 bg-paper-0 text-ink-700 text-small font-medium px-4 py-2 hover:border-ink-300 hover:bg-ink-50 hover:text-ink-900 transition-colors"
                >
                  Upload resume
                </button>
                <Link
                  href="/voice"
                  className="inline-flex items-center gap-1.5 rounded-full bg-ink-900 text-paper-0 text-small font-medium px-4 py-2 hover:bg-ink-800 transition-colors"
                >
                  15‑min call
                  <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
                </Link>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-5 pt-4 border-b border-ink-100 shrink-0">
        <button
          type="button"
          onClick={() => setTab("matches")}
          className={cn(
            "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "matches"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700"
          )}
        >
          For you
        </button>
        <button
          type="button"
          onClick={() => setTab("path")}
          className={cn(
            "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "path"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700"
          )}
        >
          Career paths
        </button>
        <button
          type="button"
          onClick={() => setTab("saved")}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
            tab === "saved"
              ? "border-ink-900 text-ink-900"
              : "border-transparent text-ink-400 hover:text-ink-700"
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
            savedJobIds={savedJobIds}
            onSavedChange={onSavedChange}
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

// ── Coaching Panel ────────────────────────────────────────────────────────────

type CoachingCard = { title: string; desc: string; prompt: string };

const COACHING_TABS: {
  id: string;
  label: string;
  Icon: React.ElementType;
  cards: CoachingCard[];
}[] = [
  {
    id: "general",
    label: "General",
    Icon: GraduationCap,
    cards: [
      { title: "Recover from a tough interview or rejection", desc: "Bad result? Turn it into one specific lesson for next time.", prompt: "I had a tough interview / rejection recently. Help me recover and turn it into a specific lesson." },
      { title: "Reflect on your job search progress",          desc: "Mid-search check-in. What's working, what's not.",         prompt: "Let's do a mid-search check-in. Help me reflect on what's working and what isn't in my job search." },
      { title: "Plan your next career move",                   desc: "Stuck deciding what's next? Map it out together.",          prompt: "I'm stuck deciding my next career move. Help me map out my options." },
      { title: "Work through career anxiety",                  desc: "Feeling stuck, behind, or restless? Talk it through.",      prompt: "I'm feeling anxious / stuck about my career. Can we talk it through?" },
      { title: "Get clarity on your career goals",             desc: "What's your work personality? Find out.",                   prompt: "Help me get clarity on my career goals and what kind of work suits me." },
    ],
  },
  {
    id: "product",
    label: "Product",
    Icon: Sparkles,
    cards: [
      { title: "Prep for a product role",        desc: "Sharpen your product thinking and case answers.", prompt: "Help me prepare for a product management role interview." },
      { title: "Build a product portfolio story", desc: "Frame your impact as crisp product narratives.",  prompt: "Help me turn my experience into a strong product portfolio story." },
    ],
  },
  {
    id: "salary",
    label: "Salary",
    Icon: IndianRupee,
    cards: [
      { title: "Know your market value",  desc: "Benchmark your CTC for your role and city.",      prompt: "What's my likely market value / CTC range for my role in India?" },
      { title: "Negotiate an offer",      desc: "Get a script for negotiating your next offer.",   prompt: "Help me negotiate a job offer. Give me a script and strategy." },
    ],
  },
  {
    id: "consulting",
    label: "Consulting",
    Icon: Briefcase,
    cards: [
      { title: "Crack a case interview",  desc: "Practice structured case-solving frameworks.",    prompt: "Let's practice a consulting case interview." },
      { title: "Build a consulting CV",   desc: "Tailor your resume for consulting roles.",        prompt: "Help me tailor my CV for consulting roles." },
    ],
  },
  {
    id: "mock",
    label: "Mock interview",
    Icon: User,
    cards: [
      { title: "Behavioural mock interview", desc: "Practice STAR-style behavioural questions.",   prompt: "Let's run a behavioural mock interview. Ask me real questions and give feedback." },
      { title: "Role-specific mock interview", desc: "Tailored to your target role and seniority.", prompt: "Run a role-specific mock interview tailored to my target role and give detailed feedback." },
    ],
  },
  {
    id: "custom",
    label: "Custom",
    Icon: SlidersHorizontal,
    cards: [
      { title: "Coach me on anything",  desc: "Bring your own topic — Aarya adapts.",  prompt: "I'd like coaching on a specific topic. Let me tell you what it is." },
    ],
  },
];

function CoachingPanel({ onSendToChat }: { onSendToChat: (text: string) => void }) {
  const [activeTab, setActiveTab] = useState(COACHING_TABS[0].id);
  const tab = COACHING_TABS.find((t) => t.id === activeTab) ?? COACHING_TABS[0];

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div className="flex items-center gap-1 px-5 pt-4 overflow-x-auto border-b border-ink-100">
        {COACHING_TABS.map((t) => {
          const isActive = t.id === activeTab;
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-2 text-small font-medium shrink-0 border-b-2 -mb-px transition-colors duration-fast",
                isActive
                  ? "border-ink-900 text-ink-900"
                  : "border-transparent text-ink-400 hover:text-ink-700"
              )}
            >
              <t.Icon className="h-4 w-4" strokeWidth={1.5} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Cards */}
      <div key={activeTab} className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-3 animate-fade-in overflow-y-auto">
        {tab.cards.map((card) => (
          <button
            key={card.title}
            onClick={() => onSendToChat(card.prompt)}
            className="group text-left rounded-xl border border-ink-200 bg-paper-0 p-4 flex flex-col gap-2 hover:border-ink-300 hover:shadow-1 transition-all duration-fast active:scale-[0.99]"
          >
            <div className="w-9 h-9 rounded-lg bg-ink-100 flex items-center justify-center">
              <tab.Icon className="h-4 w-4 text-ink-600" strokeWidth={1.5} />
            </div>
            <p className="text-small font-semibold text-ink-900 leading-snug">{card.title}</p>
            <p className="text-micro text-ink-500 leading-snug flex-1">{card.desc}</p>
            <span className="inline-flex items-center gap-1 text-small font-medium text-ink-700 group-hover:text-ink-900 transition-colors mt-1">
              Begin
              <ChevronRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" strokeWidth={2} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Toggle switch ─────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-5 w-9 rounded-full transition-colors duration-fast ease-out-soft shrink-0",
        checked ? "bg-accent" : "bg-ink-100"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-paper-1 shadow-1 transition-transform duration-fast",
          checked ? "translate-x-[18px]" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

// ── Top nav (horizontal pills) ──────────────────────────────────────────────

function TopNav({
  activePanel,
  onTogglePanel,
  pendingIntros,
  showAdminLink,
  onSignOut,
  signingOut,
}: {
  activePanel: PanelId | null;
  onTogglePanel: (id: PanelId) => void;
  pendingIntros: boolean;
  showAdminLink: boolean;
  onSignOut: () => void;
  signingOut: boolean;
}) {
  return (
    <header className="shrink-0 h-16 flex items-center gap-3 px-4 md:px-5 border-b border-ink-100 bg-paper-0">
      {/* Logo */}
      <Link
        href="/dashboard"
        className="flex items-center gap-2 shrink-0"
        aria-label="Hireloop home"
        title="Hireloop"
      >
        <div className="w-9 h-9 rounded-xl bg-ink-900 flex items-center justify-center">
          <span className="text-paper-0 text-small font-semibold">H</span>
        </div>
        <span className="hidden lg:block text-small font-semibold text-ink-900">
          Hireloop
        </span>
      </Link>

      {/* Nav pills */}
      <nav className="flex items-center gap-1 flex-1 min-w-0 overflow-x-auto">
        {RAIL_ITEMS.map((item) => {
          const isActive = activePanel === item.id;
          const showDot  = item.id === "inbox" && pendingIntros;

          return (
            <button
              key={item.id}
              aria-pressed={isActive}
              onClick={() => onTogglePanel(item.id)}
              className={cn(
                "relative inline-flex items-center gap-2 rounded-full px-3.5 py-2 shrink-0",
                "text-small font-medium transition-colors duration-fast",
                isActive
                  ? "bg-ink-900 text-paper-0"
                  : "text-ink-500 hover:text-ink-900 hover:bg-ink-50"
              )}
            >
              <item.Icon className="h-[17px] w-[17px]" strokeWidth={1.5} />
              <span>{item.label}</span>
              {showDot && (
                <span className="w-[7px] h-[7px] rounded-full bg-accent" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Right-side actions */}
      <div className="flex items-center gap-1 shrink-0">
        <NotificationDrawer
          pendingIntros={pendingIntros}
          categories={NOTIFICATION_CATEGORIES}
        />
        {showAdminLink && (
          <Link
            href="/admin"
            title="Admin"
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast"
          >
            <Shield className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </Link>
        )}
        <a
          href="https://hireloop.in/help"
          target="_blank"
          rel="noopener noreferrer"
          title="Help"
          className="w-9 h-9 rounded-full flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast"
        >
          <HelpCircle className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </a>
        <button
          onClick={onSignOut}
          disabled={signingOut}
          title="Sign out"
          className="w-9 h-9 rounded-full flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors duration-fast disabled:opacity-50"
        >
          <LogOut className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </button>
      </div>
    </header>
  );
}
