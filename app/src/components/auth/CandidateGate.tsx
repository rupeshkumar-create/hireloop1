"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchMyProfile } from "@/lib/api/profile";

const SKIP_PREFIXES = ["/onboarding", "/signup", "/auth", "/voice", "/login"];

export function CandidateGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(() =>
    SKIP_PREFIXES.some((p) => pathname?.startsWith(p)) ||
    pathname?.startsWith("/recruiter"),
  );

  useEffect(() => {
    if (!pathname) return;
    if (SKIP_PREFIXES.some((p) => pathname.startsWith(p))) {
      setReady(true);
      return;
    }
    if (pathname.startsWith("/recruiter")) {
      setReady(true);
      return;
    }

    let cancelled = false;
    setReady(false);

    fetchMyProfile()
      .then((profile) => {
        if (cancelled) return;
        if (profile.user?.role === "recruiter") {
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
        <p className="sr-only">Loading your account</p>
        <div className="h-8 w-8 rounded-full border-2 border-ink-200 border-t-ink-900 animate-spin" />
      </div>
    );
  }

  return children;
}
