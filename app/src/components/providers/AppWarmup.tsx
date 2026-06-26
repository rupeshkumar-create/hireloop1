"use client";

import { useEffect } from "react";
import { scheduleIdleWarmupRewarm, warmupChatContext } from "@/lib/chat/warmup";

/** Runs chat/voice warmup after login and on idle refresh. */
export function AppWarmup() {
  useEffect(() => {
    void warmupChatContext().catch(() => undefined);
    const stop = scheduleIdleWarmupRewarm(30_000);
    return stop;
  }, []);

  return null;
}
