"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { fetchMyProfile } from "@/lib/api/profile";
import {
  isClientOnboardingCompleteRecent,
  markClientOnboardingComplete,
  sleep,
} from "@/lib/auth/onboarding-complete";

const GATE_MAX_WAIT_MS = 12_000;
const PROFILE_FETCH_TIMEOUT_MS = 8_000;

/**
 * Prevents the onboarding wizard from flashing when activation already finished.
 * Only redirects when the API confirms onboarding_complete (with short retries
 * after POST /complete-onboarding while the profile revalidates).
 */
export function OnboardingClientGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [slowApi, setSlowApi] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const deadline = Date.now() + GATE_MAX_WAIT_MS;

    void (async () => {
      try {
        const { data } = await createClient().auth.getUser();
        const userId = data.user?.id;

        const delays = isClientOnboardingCompleteRecent(60_000)
          ? [0, 400, 900, 1800]
          : [0];

        for (const delayMs of delays) {
          if (cancelled) return;
          if (Date.now() >= deadline) break;
          if (delayMs > 0) await sleep(delayMs);

          const profile = await Promise.race([
            fetchMyProfile({ force: true }),
            sleep(PROFILE_FETCH_TIMEOUT_MS).then(() => {
              throw new Error("profile_fetch_timeout");
            }),
          ]);
          if (cancelled) return;

          if (profile.candidate?.onboarding_complete === true) {
            markClientOnboardingComplete(userId);
            window.location.replace("/dashboard");
            return;
          }
        }
      } catch (err) {
        if (!cancelled && err instanceof Error && err.message === "profile_fetch_timeout") {
          setSlowApi(true);
        }
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
      <div className="min-h-screen bg-paper-0 flex flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-small text-ink-500">Loading…</p>
        {slowApi ? (
          <p className="text-caption text-ink-400 max-w-sm">
            The server is taking longer than usual. You can continue setup below in a moment.
          </p>
        ) : null}
      </div>
    );
  }

  return children;
}
