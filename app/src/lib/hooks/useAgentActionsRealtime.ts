"use client";

/**
 * Supabase Realtime subscription for agent_actions (R7).
 * Replaces slow polling for the "Performed N actions" timeline during streaming.
 */

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";
import type { AgentAction } from "@/components/chat/ActivityTimeline";
import type { ApplicationKit } from "@/lib/api/applicationKit";
import type { MatchedJob } from "@/lib/api/matches";

type RealtimePayload = {
  onActions?: (actions: AgentAction[]) => void;
  onTurnCount?: (count: number) => void;
  onJobs?: (jobs: MatchedJob[]) => void;
  onApplicationKits?: (kits: ApplicationKit[]) => void;
  enabled?: boolean;
};

function parseResult(raw: unknown): Record<string, unknown> | null {
  if (raw == null) return null;
  if (typeof raw === "object") return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null;
    }
  }
  return null;
}

export function useAgentActionsRealtime(
  sessionId: string | null,
  userId: string | null,
  callbacks: RealtimePayload
) {
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;

  useEffect(() => {
    if (!sessionId || !userId || callbacks.enabled === false) return;

    const supabase = createClient();
    const turnActions: AgentAction[] = [];

    const channel = supabase
      .channel(`agent-actions:${sessionId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "agent_actions",
          filter: `session_id=eq.${sessionId}`,
        },
        (payload) => {
          const row = payload.new as {
            action_type?: string;
            created_at?: string;
            result?: unknown;
            user_id?: string;
          };
          if (row.user_id && row.user_id !== userId) return;

          const action: AgentAction = {
            type: row.action_type ?? "unknown",
            at: row.created_at ?? new Date().toISOString(),
          };

          const result = parseResult(row.result);
          if (row.action_type === "job_search" && result?.jobs) {
            const jobs = result.jobs as MatchedJob[];
            action.jobs = jobs;
            callbacksRef.current.onJobs?.(jobs);
          }
          if (row.action_type === "prepare_application_kit" && result?.kits) {
            const kits = result.kits as ApplicationKit[];
            callbacksRef.current.onApplicationKits?.(kits);
          }

          turnActions.unshift(action);
          callbacksRef.current.onActions?.([...turnActions]);
          callbacksRef.current.onTurnCount?.(turnActions.length);
        }
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [sessionId, userId, callbacks.enabled]);
}
