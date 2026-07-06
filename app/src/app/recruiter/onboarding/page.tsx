/**
 * Recruiter onboarding entry — shown after recruiter sign-up (LinkedIn or email).
 * Candidates are redirected to /onboarding (Aarya CV wizard).
 */

import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getServerApiBaseUrl } from "@/lib/api/base-url";
import { createClient } from "@/lib/supabase/server";
import { RecruiterOnboardingFlow } from "./RecruiterOnboardingFlow";

export const metadata: Metadata = {
  title: "Set up recruiter workspace — Hireschema",
};

export default async function RecruiterOnboardingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/signup?role=recruiter");
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (token) {
    try {
      const meRes = await fetch(`${getServerApiBaseUrl()}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (meRes.ok) {
        const me = (await meRes.json()) as { role?: string };
        if (me.role === "candidate") {
          redirect("/onboarding");
        }
      }
    } catch {
      /* non-fatal */
    }
  }

  return <RecruiterOnboardingFlow />;
}
