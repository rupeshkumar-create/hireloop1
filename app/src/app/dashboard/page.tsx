/**
 * Dashboard page — candidate home.
 */

import type { Metadata } from "next";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DashboardClient } from "./DashboardClient";
import { VALID_JOBS_TABS, VALID_PANELS, VALID_PROFILE_TABS, LEGACY_PANEL_REDIRECT, LEGACY_JOBS_TAB_REDIRECT, type JobsTab, type PanelId, type ProfileTabId } from "@/lib/dashboard/panel-types";
import { sanitizeDisplayName } from "@/lib/auth/display-name";
import { isOnboardingCompleteOnServer } from "@/lib/auth/server-onboarding";
import { canApplyOrIntro, shouldShowProfileBoosters } from "@/lib/profile/readiness";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Dashboard",
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type DashboardCandidate = {
  id: string;
  location_city: string | null;
  expected_ctc_min: number | null;
  expected_ctc_max: number | null;
  linkedin_url: string | null;
  onboarding_complete: boolean | null;
  profile_complete: boolean | null;
  current_title: string | null;
  skills: string[] | null;
  looking_for: string | null;
};

type DashboardApiProfile = {
  user?: { full_name?: string | null } | null;
  candidate?: Partial<DashboardCandidate> & { id: string } | null;
  resume_filename?: string | null;
};

function candidateFromApi(
  candidate: DashboardApiProfile["candidate"],
): DashboardCandidate | null {
  if (!candidate?.id) return null;
  return {
    id: candidate.id,
    location_city: candidate.location_city ?? null,
    expected_ctc_min: candidate.expected_ctc_min ?? null,
    expected_ctc_max: candidate.expected_ctc_max ?? null,
    linkedin_url: candidate.linkedin_url ?? null,
    onboarding_complete: candidate.onboarding_complete ?? null,
    profile_complete: candidate.profile_complete ?? null,
    current_title: candidate.current_title ?? null,
    skills: candidate.skills ?? null,
    looking_for: candidate.looking_for ?? null,
  };
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[]>>;
}) {
  const sp = await searchParams;
  const initRaw = sp.init;
  const initMessage = Array.isArray(initRaw) ? initRaw[0] : initRaw;

  // Optional ?panel= to open a specific preview panel on load (e.g. arriving
  // from the legacy /matches route → opens the Jobs panel).
  const panelRaw = sp.panel;
  const panelValue = Array.isArray(panelRaw) ? panelRaw[0] : panelRaw;
  const tabRaw = sp.tab;
  const tabValue = Array.isArray(tabRaw) ? tabRaw[0] : tabRaw;
  const profileTabRaw = sp.profile_tab;
  const profileTabValue = Array.isArray(profileTabRaw) ? profileTabRaw[0] : profileTabRaw;

  let initialPanel: PanelId | undefined;
  let initialJobsTab: JobsTab | undefined;
  let initialProfileTab: ProfileTabId | undefined;

  if (panelValue && LEGACY_PANEL_REDIRECT[panelValue]) {
    const leg = LEGACY_PANEL_REDIRECT[panelValue];
    if (leg.panel) initialPanel = leg.panel;
    if (leg.jobsTab) initialJobsTab = leg.jobsTab;
    if (leg.profileTab) initialProfileTab = leg.profileTab;
  } else if (panelValue && VALID_PANELS.includes(panelValue as PanelId)) {
    initialPanel = panelValue as PanelId;
  }

  if (tabValue && LEGACY_JOBS_TAB_REDIRECT[tabValue]) {
    const leg = LEGACY_JOBS_TAB_REDIRECT[tabValue];
    if (leg.panel) initialPanel = leg.panel;
    if (leg.jobsTab) initialJobsTab = leg.jobsTab;
    if (leg.profileTab) initialProfileTab = leg.profileTab;
  } else if (tabValue && VALID_JOBS_TABS.includes(tabValue as JobsTab)) {
    initialJobsTab = tabValue as JobsTab;
  }

  if (
    profileTabValue &&
    VALID_PROFILE_TABS.includes(profileTabValue as ProfileTabId)
  ) {
    initialProfileTab = profileTabValue as ProfileTabId;
  }

  const voiceRaw = sp.voice;
  const voiceParam = Array.isArray(voiceRaw) ? voiceRaw[0] : voiceRaw;
  const initialVoiceDeepDive = voiceParam === "deep";

  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const gmailRaw = sp.gmail;
  const gmailParam = Array.isArray(gmailRaw) ? gmailRaw[0] : gmailRaw;
  const gmailReasonRaw = sp.gmail_reason;
  const gmailReason = Array.isArray(gmailReasonRaw) ? gmailReasonRaw[0] : gmailReasonRaw;

  if (!user) {
    // Returning from Google OAuth without a session — send to sign-in with context
    // instead of a bare /signup that feels like a blank/broken page.
    const qs = new URLSearchParams({ mode: "signin", redirect: "/dashboard" });
    if (gmailParam === "error") {
      qs.set("gmail", "error");
      if (gmailReason) qs.set("gmail_reason", gmailReason);
      qs.set(
        "message",
        gmailReason === "invalid_client"
          ? "Google connect failed because app credentials are misconfigured. Sign in, then ask support to rotate GOOGLE_CLIENT_SECRET."
          : "Google connect didn't finish. Sign in, then try Connect Google again from Profile.",
      );
    } else if (gmailParam === "connected") {
      qs.set("gmail", "connected");
      qs.set("message", "Google connected — sign in to continue to your chat.");
    }
    redirect(`/signup?${qs.toString()}`);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: profile } = await (supabase as any)
    .from("users")
    .select("full_name, role")
    .eq("id", user.id)
    .is("deleted_at", null)
    .single() as { data: { full_name: string | null; role: string } | null };

  let resolvedRole = profile?.role ?? "candidate";
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;

  if (token) {
    try {
      const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (meRes.ok) {
        const me = (await meRes.json()) as { role?: string };
        if (me.role) resolvedRole = me.role;
      }
    } catch {
      /* use Supabase profile role */
    }
  }

  if (!profile && !token) {
    redirect("/onboarding");
  }

  if (resolvedRole === "recruiter") {
    redirect("/recruiter");
  }

  let apiProfileData: DashboardApiProfile | null = null;
  if (token) {
    try {
      const profileRes = await fetch(`${API_URL}/api/v1/me/profile`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (profileRes.ok) {
        apiProfileData = (await profileRes.json()) as DashboardApiProfile;
      }
    } catch {
      /* fall back to direct Supabase reads below */
    }
  }

  let candidateRaw = candidateFromApi(apiProfileData?.candidate);

  if (!candidateRaw) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data } = await (supabase as any)
      .from("candidates")
      .select(
        "id, location_city, expected_ctc_min, expected_ctc_max, linkedin_url, onboarding_complete, profile_complete, current_title, skills, looking_for",
      )
      .eq("user_id", user.id)
      .is("deleted_at", null)
      .order("updated_at", { ascending: false })
      .limit(1)
      .maybeSingle() as { data: DashboardCandidate | null };
    candidateRaw = data;
  }

  if (!candidateRaw) {
    redirect("/onboarding");
  }

  const candidateId = candidateRaw.id;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const resumeResult = await (supabase as any)
    .from("resumes")
    .select("id", { count: "exact", head: true })
    .eq("candidate_id", candidateId) as { count: number | null };

  const hasResume =
    Boolean(apiProfileData?.resume_filename) || (resumeResult.count ?? 0) > 0;

  const onboardingComplete =
    apiProfileData?.candidate
      ? apiProfileData.candidate.onboarding_complete === true
      : await isOnboardingCompleteOnServer({
          token,
          supabaseCandidate: candidateRaw,
          hasResume,
          apiBase: API_URL,
        });

  if (!onboardingComplete) {
    redirect("/onboarding");
  }

  // ── Profile readiness (frontend gates only — match APIs unchanged) ────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const voiceResult = await (supabase as any)
    .from("voice_sessions")
    .select("id", { count: "exact", head: true })
    .eq("candidate_id", candidateId)
    .eq("status", "completed") as { count: number | null };

  const hasVoiceSession = (voiceResult.count ?? 0) > 0;
  const profileForReadiness = {
    candidate: {
      location_city: candidateRaw.location_city,
      expected_ctc_min: candidateRaw.expected_ctc_min,
      expected_ctc_max: candidateRaw.expected_ctc_max,
      linkedin_url: candidateRaw.linkedin_url,
    },
  };
  const canApply = canApplyOrIntro(profileForReadiness, hasResume);
  const showProfileBoosters = shouldShowProfileBoosters(profileForReadiness, hasResume);

  // Try to surface a pre-existing session so returning users see their history.
  // This is best-effort: if the Supabase server-side session isn't available yet
  // (e.g. right after an OAuth redirect) the token may be absent and the API
  // returns 401. That's fine — the ChatInterface will create a session lazily
  // on the user's first message send, so the dashboard always renders.
  let conversationId: string | undefined;
  let canSeeAdmin = false;
  let candidateName: string | undefined =
    sanitizeDisplayName(profile?.full_name) ?? undefined;
  candidateName =
    sanitizeDisplayName(apiProfileData?.user?.full_name) ?? candidateName;
  if (token) {
    try {
      const sessRes = await fetch(`${API_URL}/api/v1/chat/sessions/primary`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (sessRes.ok) {
        const data = (await sessRes.json()) as { conversation_id?: string };
        if (data.conversation_id) {
          conversationId = data.conversation_id;
        }
      }
    } catch {
      // Non-fatal — lazy creation will handle it client-side
    }

    // Super-admin affordance: if the user is allowed to hit admin endpoints,
    // show an Admin link in the UI.
    try {
      const adminProbe = await fetch(`${API_URL}/api/v1/admin/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      canSeeAdmin = adminProbe.ok;
    } catch {
      canSeeAdmin = false;
    }
  }

  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-paper-0 text-small text-ink-500">
          Loading dashboard…
        </div>
      }
    >
      <DashboardClient
        conversationId={conversationId}
        candidateName={candidateName}
        initialInput={initMessage}
        initialPanel={initialPanel}
        canApplyOrIntro={canApply}
        hasResume={hasResume}
        hasVoiceSession={hasVoiceSession}
        showProfileBoosters={showProfileBoosters}
        initialVoiceDeepDive={initialVoiceDeepDive}
        initialJobsTab={initialJobsTab}
        initialProfileTab={initialProfileTab}
        showAdminLink={canSeeAdmin}
      />
    </Suspense>
  );
}
