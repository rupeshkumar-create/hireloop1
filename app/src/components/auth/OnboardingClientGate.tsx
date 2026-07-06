"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { fetchMyProfile } from "@/lib/api/profile";
import {
  isClientOnboardingCompleteRecent,
  markClientOnboardingComplete,
  sleep,
} from "@/lib/auth/onboarding-complete";

/**
 * Prevents the onboarding wizard from flashing when activation already finished.
 * Only redirects when the API confirms onboarding_complete (with short retries
 * after POST /complete-onboarding while the profile revalidates).
 */
export function OnboardingClientGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const { data } = await createClient().auth.getUser();
        const userId = data.user?.id;

        const delays = isClientOnboardingCompleteRecent(60_000)
          ? [0, 400, 900, 1800]
          : [0];

        for (const delayMs of delays) {
          if (cancelled) return;
          if (delayMs > 0) await sleep(delayMs);

          const profile = await fetchMyProfile({ force: true });
          if (cancelled) return;

          if (profile.candidate?.onboarding_complete === true) {
            markClientOnboardingComplete(userId);
            window.location.replace("/dashboard");
            return;
          }
        }
      } catch {
        /* show wizard */
      }

      if (!cancelled) setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen bg-paper-0 flex items-center justify-center">
        <p className="text-small text-ink-500">Loading…</p>
      </div>
    );
  }

  return children;
}
