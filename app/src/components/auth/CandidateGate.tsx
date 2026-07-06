"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  markClientOnboardingComplete,
} from "@/lib/auth/onboarding-complete";
import { fetchMyProfile } from "@/lib/api/profile";
import { isPublicPath } from "@/lib/public-routes";

/**
 * Client-side role routing only. Onboarding completion is enforced on the server
 * (dashboard + onboarding pages) so we never bounce dashboard ↔ onboarding here.
 */
export function CandidateGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!pathname || isPublicPath(pathname)) return;
    if (pathname.startsWith("/onboarding") || pathname.startsWith("/recruiter")) {
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const profile = await fetchMyProfile();
        if (cancelled) return;

        if (profile.user?.role === "recruiter") {
          if (!pathname.startsWith("/recruiter")) {
            router.replace("/recruiter/inbox");
          }
          return;
        }

        if (profile.candidate?.onboarding_complete === true) {
          markClientOnboardingComplete();
        }
      } catch {
        /* non-fatal — server layout already gated onboarding */
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  return children;
}
