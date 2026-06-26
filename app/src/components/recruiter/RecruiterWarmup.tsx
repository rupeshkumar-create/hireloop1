"use client";

import { useEffect } from "react";
import { warmupChatContext, scheduleIdleWarmupRewarm } from "@/lib/chat/warmup";

/** Prefetch candidate context for recruiter-side Nitya flows that share the graph. */
export function RecruiterWarmup() {
  useEffect(() => {
    void warmupChatContext().catch(() => undefined);
    const stop = scheduleIdleWarmupRewarm(60_000);
    return stop;
  }, []);
  return null;
}
