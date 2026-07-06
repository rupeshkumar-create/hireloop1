/**
 * Dashboard page — candidate home.
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DashboardClient } from "./DashboardClient";
import { VALID_JOBS_TABS, VALID_PANELS, LEGACY_JOBS_TAB_PANEL, type JobsTab, type PanelId } from "@/lib/dashboard/panel-types";
import { sanitizeDisplayName } from "@/lib/auth/display-name";
import { canApplyOrIntro, shouldShowProfileBoosters } from "@/lib/profile/readiness";

export const metadata: Metadata = {
  title: "Dashboard",
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

  if (!profile) {
    redirect("/onboarding");
  }

  let resolvedRole = profile.role;
  const {
    data: { session: earlySession },
  } = await supabase.auth.getSession();
  const earlyToken = earlySession?.access_token;
  if (earlyToken) {
    try {
      const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${earlyToken}` },
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

  if (resolvedRole === "recruiter") {
    redirect("/recruiter");
  }

  // Supabase TS: .is("deleted_at", null) can infer 'never' on strict builds.
  // Use maybeSingle() + explicit cast to avoid the inference bug.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: candidateRaw } = await (supabase as any)
    .from("candidates")
    .select(
      "id, location_city, expected_ctc_min, expected_ctc_max, linkedin_url, onboarding_complete",
    )
    .eq("user_id", user.id)
    .is("deleted_at", null)
    .maybeSingle() as {
    data: {
      id: string;
      location_city: string | null;
      expected_ctc_min: number | null;
      expected_ctc_max: number | null;
      linkedin_url: string | null;
      onboarding_complete: boolean | null;
    } | null;
  };

  if (!candidateRaw) {
    redirect("/onboarding");
  }

  if (candidateRaw.onboarding_complete !== true) {
    redirect("/onboarding");
  }

  const candidateId = candidateRaw.id;

  // ── Profile readiness (frontend gates only — match APIs unchanged) ────────
  const [resumeResult, voiceResult] = await Promise.all([
    // Any resume uploaded for this candidate
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (supabase as any)
      .from("resumes")
      .select("id", { count: "exact", head: true })
      .eq("candidate_id", candidateId) as Promise<{ count: number | null }>,

    // Any completed Aarya voice session
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (supabase as any)
      .from("voice_sessions")
      .select("id", { count: "exact", head: true })
      .eq("candidate_id", candidateId)
      .eq("status", "completed") as Promise<{ count: number | null }>,
  ]);

  const hasResume = (resumeResult.count ?? 0) > 0;
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
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;

  let conversationId: string | undefined;
  let canSeeAdmin = false;
  let candidateName: string | undefined =
    sanitizeDisplayName(profile?.full_name) ?? undefined;
  if (token) {
    try {
      const profileRes = await fetch(`${API_URL}/api/v1/me/profile`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (profileRes.ok) {
        const profileData = (await profileRes.json()) as {
          user?: { full_name?: string | null };
        };
        candidateName =
          sanitizeDisplayName(profileData.user?.full_name) ?? candidateName;
      }
    } catch {
      /* use Supabase users.full_name */
    }

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
