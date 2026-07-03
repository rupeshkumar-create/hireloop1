"use client";

import { ArrowRight, Briefcase, Inbox, Route } from "lucide-react";
import type { PanelId } from "@/lib/dashboard/panel-types";
import type { MyProfileData } from "@/lib/api/profile";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui";

type NextAction = {
  label: string;
  hint: string;
  onClick: () => void;
};

function profileCompletenessPercent(
  profile: MyProfileData | null,
  hasCareerPath: boolean,
  matchCount: number | null,
  intelCompleteness: number | null,
): number | null {
  if (intelCompleteness != null) {
    return Math.min(100, Math.max(0, Math.round(intelCompleteness)));
  }
  if (!profile) return null;

  let score = 0;
  if (profile.resume_filename) score += 30;
  if (profile.candidate?.profile_complete) score += 30;
  if (hasCareerPath) score += 20;
  if ((matchCount ?? 0) > 0) score += 20;
  return score;
}

function deriveNextAction({
  profile,
  matchCount,
  onOpenPanel,
}: {
  profile: MyProfileData | null;
  matchCount: number | null;
  onOpenPanel: (id: PanelId) => void;
}): NextAction {
  if (!profile?.resume_filename) {
    return {
      label: "Upload your resume",
      hint: "Aarya uses it to score matches and draft intros.",
      onClick: () => onOpenPanel("profile"),
    };
  }
  if (!profile.candidate?.profile_complete) {
    return {
      label: "Complete your profile",
      hint: "Add title, city, and expected CTC so matches are accurate.",
      onClick: () => onOpenPanel("profile"),
    };
  }
  if (matchCount != null && matchCount > 0) {
    return {
      label: "View your matches",
      hint: `${matchCount} roles ranked for you — start with the strongest fits.`,
      onClick: () => onOpenPanel("jobs"),
    };
  }
  return {
    label: "Show me jobs",
    hint: "Start with resume-based matches; career paths can refine the direction later.",
    onClick: () => onOpenPanel("jobs"),
  };
}

function ProgressRing({ percent }: { percent: number | null }) {
  const value = percent ?? 0;
  const r = 22;
  const c = 2 * Math.PI * r;
  const offset = c - (value / 100) * c;

  return (
    <div className="relative h-14 w-14 shrink-0" aria-label={`Profile ${value}% complete`}>
      <svg className="h-14 w-14 -rotate-90" viewBox="0 0 48 48" aria-hidden>
        <circle cx="24" cy="24" r={r} fill="none" stroke="currentColor" strokeWidth="4" className="text-ink-200" />
        <circle
          cx="24"
          cy="24"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          className="text-accent transition-[stroke-dashoffset] duration-base ease-out-soft"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-micro font-semibold text-ink-900">
        {percent == null ? "—" : `${value}%`}
      </span>
    </div>
  );
}

export function HomeMissionHero({
  firstName,
  profile,
  hasCareerPath,
  jobCount,
  introCount,
  intelCompleteness,
  onOpenPanel,
}: {
  firstName: string;
  profile: MyProfileData | null;
  hasCareerPath: boolean;
  jobCount: number | null;
  introCount: number | null;
  intelCompleteness: number | null;
  onOpenPanel: (id: PanelId) => void;
}) {
  const completeness = profileCompletenessPercent(
    profile,
    hasCareerPath,
    jobCount,
    intelCompleteness,
  );
  const next = deriveNextAction({
    profile,
    matchCount: jobCount,
    onOpenPanel,
  });

  const stats = [
    {
      label: "Matches",
      value: jobCount,
      Icon: Briefcase,
      onClick: () => onOpenPanel("jobs"),
    },
    {
      label: "Intros",
      value: introCount,
      Icon: Inbox,
      onClick: () => onOpenPanel("inbox"),
    },
  ];

  return (
    <div className="rounded-xl border border-ink-100 bg-gradient-to-br from-paper-1 to-ink-50 p-4 shadow-sm space-y-4">
      <div className="flex items-start gap-3">
        <ProgressRing percent={completeness} />
        <div className="min-w-0 flex-1 pt-0.5">
          <p className="text-micro font-medium uppercase tracking-wide text-ink-400">
            Mission control
          </p>
          <h3 className="text-h2 font-semibold text-ink-900 truncate">
            Welcome back, {firstName}
          </h3>
          <p className="text-small text-ink-500 mt-0.5">
            Chat with Aarya on the right — everything else starts here.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {stats.map(({ label, value, Icon, onClick }) => (
          <button
            key={label}
            type="button"
            onClick={onClick}
            className={cn(
              "flex items-center gap-2 rounded-lg border border-ink-100 bg-paper-0 px-3 py-2.5",
              "text-left transition-colors hover:border-ink-200 hover:bg-ink-50",
            )}
          >
            <Icon className="h-4 w-4 text-ink-500 shrink-0" strokeWidth={1.5} />
            <div className="min-w-0">
              <p className="text-micro text-ink-500">{label}</p>
              <p className="text-h3 font-semibold text-ink-900 leading-none">
                {value == null && label === "Matches" ? "Start" : value == null ? "…" : value}
              </p>
            </div>
          </button>
        ))}
      </div>

      <div className="rounded-lg border border-accent/25 bg-paper-0 px-4 py-3 space-y-2">
        <div className="flex items-center gap-2 text-micro font-medium text-accent">
          <Route className="h-3.5 w-3.5" strokeWidth={1.5} />
          Next step
        </div>
        <p className="text-small font-semibold leading-snug text-ink-900">{next.label}</p>
        <p className="text-micro text-ink-500 leading-snug">{next.hint}</p>
        <Button
          variant="primary"
          size="sm"
          onClick={next.onClick}
          rightIcon={<ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />}
          className="mt-1"
        >
          Continue
        </Button>
      </div>
    </div>
  );
}
