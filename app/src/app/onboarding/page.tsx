/**
 * Onboarding entry — shown after candidate sign-up (LinkedIn or email).
 *
 * Steps (client-side in OnboardingFlow v2):
 *   0  Welcome
 *   1  Activate (CV + market + DPDP consent)
 *
 * Phone verification is optional (Settings) — not a signup gate.
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { resolveSignupMethod } from "@/lib/auth/signup-method";
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

  // Prefer résumé-derived name from the API over email-local-part on users.full_name.
  let candidateName: string | undefined;
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
        candidateName = profileData.user?.full_name ?? undefined;
      }
    } catch {
      /* non-fatal */
    }
  }
  if (!candidateName) {
    try {
      const supabase = await createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
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
  }

  const signupMethod = resolveSignupMethod(user);

  return (
    <OnboardingFlow candidateName={candidateName} signupMethod={signupMethod} />
  );
}
