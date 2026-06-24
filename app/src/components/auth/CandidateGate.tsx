"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchMyProfile } from "@/lib/api/profile";

const SKIP_PREFIXES = ["/onboarding", "/signup", "/auth", "/voice"];

export function CandidateGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!pathname) return;
    if (SKIP_PREFIXES.some((p) => pathname.startsWith(p))) return;
    if (pathname.startsWith("/recruiter")) return;

    fetchMyProfile()
      .then((profile) => {
        if (profile.user?.role === "recruiter") return;
        const done = profile.candidate?.onboarding_complete === true;
        if (!done) {
          router.replace("/onboarding");
        }
      })
      .catch(() => {
        /* API down — don't hard-block */
      });
  }, [pathname, router]);

  return children;
}
