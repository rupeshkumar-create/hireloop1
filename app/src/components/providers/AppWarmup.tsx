"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { scheduleIdleWarmupRewarm, warmupChatContext } from "@/lib/chat/warmup";
import { isPublicPath } from "@/lib/public-routes";

/** Runs chat/voice warmup after login — skipped on public/marketing routes. */
export function AppWarmup() {
  const pathname = usePathname();

  useEffect(() => {
    if (isPublicPath(pathname)) return;
    void warmupChatContext().catch(() => undefined);
    const stop = scheduleIdleWarmupRewarm(30_000);
    return stop;
  }, [pathname]);

  return null;
}
