/**
 * Dashboard page — candidate home.
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DashboardClient } from "./DashboardClient";

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
  const VALID_PANELS = ["home", "inbox", "profile", "jobs", "coaching"] as const;
  type PanelId = (typeof VALID_PANELS)[number];
  const initialPanel = VALID_PANELS.includes(panelValue as PanelId)
    ? (panelValue as PanelId)
    : undefined;

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
    .select("id")
    .eq("user_id", user.id)
    .is("deleted_at", null)
    .maybeSingle() as { data: { id: string } | null };

  if (!candidateRaw) {
    redirect("/onboarding");
  }

  const candidateId = (candidateRaw as { id: string }).id;

  // ── Gate hint (resume OR completed voice session) ───────────────────────
  // Jobs feed (/matches) is access-gated. We surface the same two unlock
  // paths on the dashboard so users don't miss it.
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
  const isUnlocked = hasResume || hasVoiceSession;

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
  if (token) {
    try {
      const sessRes = await fetch(`${API_URL}/api/v1/chat/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (sessRes.ok) {
        const sessions: Array<{ id: string }> = await sessRes.json();
        if (sessions.length > 0) {
          conversationId = sessions[0].id;
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
      candidateName={profile?.full_name ?? undefined}
      initialInput={initMessage}
      initialPanel={initialPanel}
      showUnlockJobsCta={!isUnlocked}
      showAdminLink={canSeeAdmin}
    />
  );
}
