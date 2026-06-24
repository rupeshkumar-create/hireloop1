"use client";

/**
 * ActivityTimeline — the "<Agent> performed N actions / Recent activity"
 * disclosure shared by Aarya (candidate chat) and Nitya (recruiter intake).
 *
 * Data comes from the agent_actions table via the chat/actions endpoints.
 * Each tool call is mapped to a human-readable label + icon, with a relative
 * timestamp, rendered as a vertical timeline.
 */

import { useState } from "react";
import {
  Briefcase,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  Mail,
  Mic,
  PenLine,
  RefreshCw,
  Search,
  Send,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserPlus,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";

/** A single tool call an agent made during a turn. */
import type { MatchedJob } from "@/lib/api/matches";

export type AgentAction = {
  type: string;
  at: string;
  jobs?: MatchedJob[];
};

/** Map a raw agent action_type to a human label + icon for the timeline. */
export function actionMeta(type: string): { label: string; Icon: LucideIcon } {
  switch (type) {
    // ── Aarya (candidate) ──────────────────────────────────────────────
    case "profile_read":
      return { label: "Read your profile", Icon: FileText };
    case "profile_update":
    case "update_profile":
      return { label: "Updated your profile", Icon: CheckCircle };
    case "job_search":
      return { label: "Searching live roles in India", Icon: Search };
    case "build_career_path":
      return { label: "Building your career path", Icon: Target };
    case "get_match_score":
    case "match_score":
      return { label: "Scored your job match", Icon: Target };
    case "request_intro":
      return { label: "Requested a warm intro", Icon: Send };
    case "direct_apply":
      return { label: "Applied to the role", Icon: Briefcase };
    case "save_job":
      return { label: "Saved a job for later", Icon: Briefcase };
    case "prepare_application_kit":
      return { label: "Prepared your application kit", Icon: FileText };
    case "update_job_preferences":
      return { label: "Updated job search preferences", Icon: SlidersHorizontal };
    case "voice_response":
      return { label: "Replied by voice", Icon: Mic };

    // ── Nitya (recruiter) ──────────────────────────────────────────────
    case "lookup_intro_request":
      return { label: "Looked up the intro request", Icon: Search };
    case "candidate_lookup":
      return { label: "Searched candidates", Icon: Users };
    case "enrich_hiring_manager":
      return { label: "Enriched the hiring manager", Icon: UserPlus };
    case "draft_intro_email":
    case "draft_email":
      return { label: "Drafted the intro email", Icon: PenLine };
    case "send_intro_email":
    case "send_via_gmail":
      return { label: "Sent the intro via Gmail", Icon: Mail };
    case "update_intro_status":
      return { label: "Updated the intro status", Icon: RefreshCw };
    case "recruiter_chat_turn":
      return { label: "Worked on the hiring brief", Icon: Sparkles };

    default:
      return {
        // Humanise snake_case → "Sentence case".
        label: type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()),
        Icon: Zap,
      };
  }
}

/** "just now" / "2m ago" / "3h ago" / "5d ago" from an ISO timestamp. */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = Math.max(0, Date.now() - then);
  const s = Math.floor(diff / 1000);
  if (s < 45) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function ActivityTimeline({
  count,
  actions,
  agentName = "Aarya",
}: {
  count: number;
  actions: AgentAction[];
  agentName?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="my-1 space-y-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 transition-colors"
      >
        <Zap className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
        {agentName} performed {count} action{count !== 1 ? "s" : ""}
        {open ? (
          <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
        ) : (
          <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
        )}
      </button>

      {open && (
        <div className="ml-1.5 rounded-lg border border-ink-100 bg-paper-1 p-3 animate-slide-up">
          <p className="mb-2.5 text-micro uppercase text-ink-400">
            Recent activity
          </p>

          {actions.length === 0 ? (
            <div className="flex items-center gap-2 text-small text-ink-500">
              <CheckCircle className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
              Finished
            </div>
          ) : (
            <ol className="relative space-y-3">
              {/* Vertical connector line */}
              <span className="absolute left-[7px] top-1 bottom-1 w-px bg-ink-100" />
              {actions.map((action, i) => {
                const { label, Icon } = actionMeta(action.type);
                return (
                  <li
                    key={`${action.type}-${action.at}-${i}`}
                    className="relative flex items-start gap-2.5"
                  >
                    <span className="relative z-10 mt-0.5 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full bg-paper-1 ring-1 ring-ink-100">
                      <Icon className="h-3 w-3 text-accent" strokeWidth={1.75} />
                    </span>
                    <span className="text-small text-ink-700 leading-tight">
                      {label}
                    </span>
                    <span className="ml-auto flex items-center gap-1 text-micro text-ink-400 shrink-0">
                      <Clock className="h-2.5 w-2.5" strokeWidth={1.5} />
                      {relativeTime(action.at)}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
