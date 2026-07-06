"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  clearClientOnboardingComplete,
  isClientOnboardingCompleteRecent,
  sleep,
} from "@/lib/auth/onboarding-complete";
import { fetchMyProfile } from "@/lib/api/profile";
import { isPublicPath } from "@/lib/public-routes";

async function isOnboardingComplete(): Promise<boolean> {
  const profile = await fetchMyProfile({ force: true });
  return profile.candidate?.onboarding_complete === true;
}

async function resolveOnboardingComplete(
  optimistic: boolean,
): Promise<boolean> {
  if (await isOnboardingComplete()) {
    return true;
  }
  if (!optimistic) {
    return false;
  }
  for (const delayMs of [800, 1500, 2500]) {
    await sleep(delayMs);
    if (await isOnboardingComplete()) {
      return true;
    }
  }
  return false;
}

export function CandidateGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(() => isPublicPath(pathname));

  useEffect(() => {
    if (!pathname) return;
    if (isPublicPath(pathname)) {
      setReady(true);
      return;
    }
    if (pathname.startsWith("/recruiter")) {
      setReady(true);
      return;
    }

    let cancelled = false;
    const optimistic = isClientOnboardingCompleteRecent();
    setReady(optimistic);

    void (async () => {
      try {
        const profile = await fetchMyProfile({ force: true });
        if (cancelled) return;

        if (profile.user?.role === "recruiter") {
          if (pathname?.startsWith("/onboarding")) {
            router.replace("/recruiter/onboarding");
            return;
          }
          if (!pathname?.startsWith("/recruiter")) {
            router.replace("/recruiter/inbox");
            return;
          }
          setReady(true);
          return;
        }

        let done = profile.candidate?.onboarding_complete === true;
        if (!done) {
          done = await resolveOnboardingComplete(optimistic);
        }
        if (cancelled) return;

        if (done) {
          clearClientOnboardingComplete();
          setReady(true);
          return;
        }

        if (optimistic) {
          // User just finished onboarding — don't loop them back while API catches up.
          setReady(true);
          return;
        }

        router.replace("/onboarding");
      } catch {
        if (!cancelled) {
          setReady(true);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (!ready) {
    return (
      <div
        className="min-h-screen flex items-center justify-center bg-paper-0"
        role="status"
        aria-live="polite"
      >
        <p className="sr-only">Loading your account</p>
        <div className="h-8 w-8 rounded-full border-2 border-ink-200 border-t-ink-900 animate-spin" />
      </div>
    );
  }

  return children;
}
