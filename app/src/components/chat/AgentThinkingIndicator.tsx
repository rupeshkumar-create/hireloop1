"use client";

/**
 * Animated status while Aarya is working — cycles friendly labels and
 * surfaces live tool activity (job search, profile read, etc.) when available.
 */

import { useEffect, useMemo, useState } from "react";
import { FileText, Search, Sparkles, type LucideIcon } from "@/components/brand/icons";
import {
  JOB_DISCOVERY_FALLBACK_LABELS,
  ingestProgressLabel,
} from "@/lib/chat/jobDiscovery";
import { cn } from "@/lib/utils";
import { actionMeta, type AgentAction } from "./ActivityTimeline";

type AgentThinkingIndicatorProps = {
  actions?: AgentAction[];
  /** Total agent_actions count when the user sent this message. */
  actionBaseline?: number;
  /** Current total from the actions poll. */
  actionCount?: number;
  className?: string;
  variant?: "thinking" | "processing" | "jobDiscovery";
  /** Fixed label (skips rotation). */
  label?: string;
};

type Phase = { label: string; Icon: LucideIcon };

const THINKING_PHASES: Phase[] = [
  { label: "Thinking", Icon: Sparkles },
  { label: "Understanding your question", Icon: Sparkles },
  { label: "Reading your resume", Icon: FileText },
  { label: "Checking your matches", Icon: FileText },
  { label: "Preparing a response", Icon: Sparkles },
];

const PROCESSING_PHASES: Phase[] = [
  { label: "Processing your resume", Icon: FileText },
  { label: "Extracting skills and experience", Icon: FileText },
  { label: "Updating your profile", Icon: Sparkles },
];

function jobDiscoveryPhases(): Phase[] {
  return JOB_DISCOVERY_FALLBACK_LABELS.map((label) => ({
    label,
    Icon: Search,
  }));
}

function phaseFromLiveAction(actions: AgentAction[]): Phase | null {
  const newest = actions[0];
  if (!newest?.type) return null;
  const then = new Date(newest.at).getTime();
  if (Number.isNaN(then) || Date.now() - then > 60_000) return null;
  if (newest.type === "job_ingest_progress") {
    const live = ingestProgressLabel(newest.progress);
    if (live) {
      return { label: stripTrailingEllipsis(live), Icon: Search };
    }
  }
  const { label, Icon } = actionMeta(newest.type);
  return { label: label.replace(/…$/, ""), Icon };
}

function stripTrailingEllipsis(text: string): string {
  return text.replace(/\.{3}$|…$/u, "").trim();
}

function TypingDots({ className }: { className?: string }) {
  return (
    <span
      className={cn("inline-flex items-center gap-[3px] self-center", className)}
      aria-hidden
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-accent/80 animate-typing-dot"
          style={{ animationDelay: `${i * 0.14}s` }}
        />
      ))}
    </span>
  );
}

export function AgentThinkingIndicator({
  actions = [],
  actionBaseline = 0,
  actionCount = 0,
  className,
  variant = "thinking",
  label,
}: AgentThinkingIndicatorProps) {
  const [phaseIndex, setPhaseIndex] = useState(0);

  const phases =
    variant === "processing"
      ? PROCESSING_PHASES
      : variant === "jobDiscovery"
        ? jobDiscoveryPhases()
        : THINKING_PHASES;

  const livePhase = useMemo(() => {
    if (label) {
      return {
        label: stripTrailingEllipsis(label),
        Icon: variant === "processing" ? FileText : Search,
      };
    }
    if (actionCount > actionBaseline && actions.length > 0) {
      return phaseFromLiveAction(actions);
    }
    return null;
  }, [actions, actionBaseline, actionCount, label, variant]);

  const displayPhase = livePhase ?? phases[phaseIndex % phases.length];
  const isLive = Boolean(livePhase && !label);

  useEffect(() => {
    if (livePhase || label) return;
    const id = window.setInterval(() => {
      setPhaseIndex((i) => i + 1);
    }, 2800);
    return () => window.clearInterval(id);
  }, [livePhase, label]);

  const { label: statusLabel, Icon } = displayPhase;

  return (
    <div
      className={cn("flex items-end gap-3 animate-fade-in", className)}
      role="status"
      aria-live="polite"
      aria-label={`${statusLabel}…`}
    >
      <div
        className={cn(
          "relative flex items-center gap-3 rounded-2xl rounded-bl-sm",
          "border border-ink-100 bg-paper-1 px-3.5 py-2.5 shadow-sm",
          "w-full min-w-[168px]"
        )}
      >
        <div className="relative shrink-0" aria-hidden>
          <span
            className={cn(
              "absolute -inset-1 rounded-full bg-accent/20",
              isLive ? "animate-pulse" : "animate-[pulse_2.4s_ease-in-out_infinite]"
            )}
          />
          <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-ink-900">
            <Icon className="h-3.5 w-3.5 text-paper-0" strokeWidth={1.75} />
          </span>
        </div>

        <div className="flex min-w-0 items-center gap-2">
          <p
            key={statusLabel}
            className="text-small font-medium text-ink-700 truncate animate-slide-up"
          >
            {statusLabel}
          </p>
          <TypingDots />
        </div>
      </div>
    </div>
  );
}
