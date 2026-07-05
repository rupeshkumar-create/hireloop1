"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchMyProfile } from "@/lib/api/profile";
import { isPublicPath } from "@/lib/public-routes";

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
    setReady(false);

    const timeout = window.setTimeout(() => {
      if (!cancelled) setReady(true);
    }, 12_000);

    fetchMyProfile()
      .then((profile) => {
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
        const done = profile.candidate?.onboarding_complete === true;
        if (!done) {
          router.replace("/onboarding");
          return;
        }
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      })
      .finally(() => {
        window.clearTimeout(timeout);
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
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
