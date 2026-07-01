/**
 * Onboarding entry — shown after LinkedIn sign-in for candidates.
 *
 * Steps (client-side in OnboardingFlow v2):
 *   0  Welcome
 *   1  Activate (CV + market + DPDP consent)
 *
 * Phone verification is optional (Settings) — not a signup gate.
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { OnboardingFlow } from "./OnboardingFlow";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const metadata: Metadata = {
  title: "Get started — Hireloop",
};

export default async function OnboardingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/signup");
  }

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
        if (me.role === "recruiter") {
          redirect("/recruiter");
        }
      }
    } catch {
      /* non-fatal */
    }
  }

  // Fetch candidate name so the unlock choice can personalise the greeting.
  // Failure is non-fatal — the flow still renders without a name.
  let candidateName: string | undefined;
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      // Supabase client isn't generated with the DB schema here, so `.from` is
      // untyped; we assert the row shape on the result below instead of `any`.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const { data } = await (supabase as any)
        .from("users")
        .select("full_name")
        .eq("id", user.id)
        .single() as { data: { full_name: string | null } | null };
      candidateName = data?.full_name ?? undefined;
    }
  } catch {
    // Swallow — not blocking
  }

  return <OnboardingFlow candidateName={candidateName} />;
}
