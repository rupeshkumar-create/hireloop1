"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchRecruiterProfile } from "@/lib/api/recruiter";

export function RecruiterGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (pathname?.startsWith("/recruiter/onboarding")) return;
    if (pathname?.startsWith("/recruiter/invite")) return;

    fetchRecruiterProfile()
      .then((p) => {
        if (!p.onboarding_complete) {
          router.replace("/recruiter/onboarding");
        }
      })
      .catch(() => {
        /* API may be down — don't block */
      });
  }, [pathname, router]);

  return children;
}
