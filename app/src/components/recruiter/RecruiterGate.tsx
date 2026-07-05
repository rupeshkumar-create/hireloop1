"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchMyProfile } from "@/lib/api/profile";
import { fetchRecruiterProfile } from "@/lib/api/recruiter";

export function RecruiterGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(
    () =>
      pathname?.startsWith("/recruiter/onboarding") ||
      pathname?.startsWith("/recruiter/invite"),
  );

  useEffect(() => {
    if (pathname?.startsWith("/recruiter/onboarding")) {
      setReady(true);
      return;
    }
    if (pathname?.startsWith("/recruiter/invite")) {
      setReady(true);
      return;
    }

    let cancelled = false;
    setReady(false);

    fetchMyProfile()
      .then((profile) => {
        if (cancelled) return;
        if (profile.user?.role === "candidate") {
          router.replace("/onboarding");
          return;
        }
        return fetchRecruiterProfile();
      })
      .then((p) => {
        if (cancelled || !p) return;
        if (!p.onboarding_complete) {
          router.replace("/recruiter/onboarding");
          return;
        }
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });

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
        <p className="sr-only">Loading recruiter workspace</p>
        <div className="h-8 w-8 rounded-full border-2 border-ink-200 border-t-ink-900 animate-spin" />
      </div>
    );
  }

  return children;
}
