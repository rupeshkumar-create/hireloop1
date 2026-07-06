/**
 * Dashboard page — candidate home.
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DashboardClient } from "./DashboardClient";
import { VALID_JOBS_TABS, VALID_PANELS, LEGACY_JOBS_TAB_PANEL, type JobsTab, type PanelId } from "@/lib/dashboard/panel-types";
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

  let initialPanel = VALID_PANELS.includes(panelValue as PanelId)
    ? (panelValue as PanelId)
    : undefined;

  // Legacy ?tab=path|tracker under Matches → dedicated sidebar panels.
  if (tabValue && tabValue in LEGACY_JOBS_TAB_PANEL) {
    initialPanel = LEGACY_JOBS_TAB_PANEL[tabValue];
  }

  const initialJobsTab = VALID_JOBS_TABS.includes(tabValue as JobsTab)
    ? (tabValue as JobsTab)
    : undefined;

  const voiceRaw = sp.voice;
  const voiceParam = Array.isArray(voiceRaw) ? voiceRaw[0] : voiceRaw;
  const initialVoiceDeepDive = voiceParam === "deep";

  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/signup");
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
      showAdminLink={canSeeAdmin}
    />
  );
}
