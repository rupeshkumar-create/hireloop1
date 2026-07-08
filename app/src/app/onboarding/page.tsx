/**
 * Onboarding entry — candidate sign-up only (Aarya CV wizard).
 * Recruiters are redirected to /recruiter/onboarding (Nitya workspace setup).
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getServerApiBaseUrl } from "@/lib/api/base-url";
import { resolveSignupMethod } from "@/lib/auth/signup-method";
import { displayNameFromSupabaseUser } from "@/lib/auth/display-name";
import { shouldRedirectOnboardingToDashboard } from "@/lib/auth/server-onboarding";
import { createClient } from "@/lib/supabase/server";
import { OnboardingClientGate } from "@/components/auth/OnboardingClientGate";
import { OnboardingFlow } from "./OnboardingFlow";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Get started — Hireschema",
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
  const apiBase = getServerApiBaseUrl();
  const serverFetchTimeoutMs = 12_000;
  if (token) {
    try {
      const meRes = await fetch(`${apiBase}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(serverFetchTimeoutMs),
      });
      if (meRes.ok) {
        const me = (await meRes.json()) as { role?: string };
        if (me.role === "recruiter") {
          redirect("/recruiter/onboarding");
        }
      }
    } catch {
      /* non-fatal */
    }

    if (await shouldRedirectOnboardingToDashboard({ token, apiBase })) {
      redirect("/dashboard");
    }
  }

  let candidateName: string | undefined = displayNameFromSupabaseUser(user);

  if (token) {
    try {
      const profileRes = await fetch(`${apiBase}/api/v1/me/profile`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(serverFetchTimeoutMs),
      });
      if (profileRes.ok) {
        const profileData = (await profileRes.json()) as {
          user?: { full_name?: string | null };
        };
        candidateName = profileData.user?.full_name?.trim() || candidateName;
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
        candidateName = data?.full_name?.trim() || candidateName;
      }
    } catch {
      // Swallow — not blocking
    }
  }

  const signupMethod = resolveSignupMethod(user);

  return (
    <OnboardingClientGate>
      <OnboardingFlow candidateName={candidateName} signupMethod={signupMethod} />
    </OnboardingClientGate>
  );
}
