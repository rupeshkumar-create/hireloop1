"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  clearClientOnboardingComplete,
  markClientOnboardingComplete,
} from "@/lib/auth/onboarding-complete";
import { fetchMyProfile } from "@/lib/api/profile";
import { createClient } from "@/lib/supabase/client";
import { isPublicPath } from "@/lib/public-routes";

function hasOAuthParams(searchParams: URLSearchParams | null): boolean {
  if (!searchParams) return false;
  return (
    searchParams.has("code") ||
    searchParams.has("token_hash") ||
    searchParams.has("error") ||
    searchParams.has("error_description")
  );
}

/**
 * Client-side role routing only. Onboarding completion is enforced on the server
 * (dashboard + onboarding pages) so we never bounce dashboard ↔ onboarding here.
 */
export function CandidateGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (!pathname) return;

    // Public listings (/r/*, /p/*, legal, auth) must stay reachable even when a
    // recruiter is logged in — otherwise "View live job" bounces to /recruiter.
    if (isPublicPath(pathname)) return;

    // OAuth return is handled by middleware + OAuthReturnHandler → /auth/callback.
    if (hasOAuthParams(searchParams)) return;

    const isMarketingEntry = pathname === "/" || pathname === "/signup";

    let cancelled = false;
    void (async () => {
      try {
        const { data: authData } = await createClient().auth.getUser();
        const userId = authData.user?.id;

        if (!userId) return;

        const profile = await fetchMyProfile();
        if (cancelled) return;

        if (profile.user?.role === "recruiter") {
          if (isMarketingEntry || !pathname.startsWith("/recruiter")) {
            router.replace("/recruiter/onboarding");
          }
          return;
        }

        if (profile.candidate?.onboarding_complete === true) {
          markClientOnboardingComplete(userId);
          if (isMarketingEntry) {
            router.replace("/dashboard");
          }
        } else if (userId) {
          clearClientOnboardingComplete();
          if (isMarketingEntry) {
            router.replace("/onboarding");
          }
        }
      } catch {
        /* non-fatal — server layout already gated onboarding */
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname, router, searchParams]);

  useEffect(() => {
    if (!pathname || isPublicPath(pathname)) return;
    if (pathname.startsWith("/onboarding") || pathname.startsWith("/recruiter")) {
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const { data: authData } = await createClient().auth.getUser();
        const userId = authData.user?.id;
        const profile = await fetchMyProfile();
        if (cancelled) return;

        if (profile.user?.role === "recruiter") {
          if (!pathname.startsWith("/recruiter")) {
            router.replace("/recruiter/inbox");
          }
          return;
        }

        if (profile.candidate?.onboarding_complete === true) {
          markClientOnboardingComplete(userId);
        } else if (userId) {
          clearClientOnboardingComplete();
        }
      } catch {
        /* non-fatal */
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  return children;
}
