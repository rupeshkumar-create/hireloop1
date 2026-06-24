"use client";

/**
 * NextBestStep — single guided progression strip for the candidate journey.
 *
 *   Resume → Profile → Career paths → Job matches
 */

import { Briefcase, Check, Circle, Route, Upload, User } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MyProfileData } from "@/lib/api/profile";
import { Card, CardBody } from "@/components/ui";

type StepId = "resume" | "profile" | "paths" | "matches";

type StepDef = {
  id: StepId;
  label: string;
  Icon: React.ElementType;
};

const STEPS: StepDef[] = [
  { id: "resume", label: "Resume", Icon: Upload },
  { id: "profile", label: "Profile", Icon: User },
  { id: "paths", label: "Career paths", Icon: Route },
  { id: "matches", label: "Matches", Icon: Briefcase },
];

export function NextBestStep({
  profile,
  hasCareerPath,
  matchCount,
  className,
}: {
  profile: MyProfileData | null;
  hasCareerPath: boolean;
  matchCount: number | null;
  className?: string;
}) {
  if (!profile) return null;

  const resumeDone = Boolean(profile.resume_filename);
  const profileDone = profile.candidate?.profile_complete === true;
  const pathsDone = hasCareerPath;
  const matchesDone = (matchCount ?? 0) > 0;

  const done: Record<StepId, boolean> = {
    resume: resumeDone,
    profile: profileDone,
    paths: pathsDone,
    matches: matchesDone,
  };

  const allDone = STEPS.every((s) => done[s.id]);
  if (allDone) return null;

  const currentIdx = STEPS.findIndex((s) => !done[s.id]);

  return (
    <Card className={className}>
      <CardBody className="space-y-3">
        <div>
          <p className="text-small font-semibold text-ink-900">Your next steps</p>
          <p className="text-micro text-ink-500 mt-0.5">
            Aarya works best when you complete these in order.
          </p>
        </div>
        <ol className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-0">
          {STEPS.map((step, i) => {
            const isDone = done[step.id];
            const isCurrent = i === currentIdx;
            return (
              <li
                key={step.id}
                className={cn(
                  "flex items-center gap-2 sm:flex-1 min-w-0",
                  i < STEPS.length - 1 && "sm:pr-2"
                )}
              >
                <div
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-2 py-1.5 w-full min-w-0",
                    isCurrent && "bg-ink-50 ring-1 ring-ink-200"
                  )}
                >
                  {isDone ? (
                    <Check className="h-4 w-4 text-ink-900 shrink-0" strokeWidth={2} />
                  ) : (
                    <Circle
                      className={cn(
                        "h-4 w-4 shrink-0",
                        isCurrent ? "text-ink-900" : "text-ink-300"
                      )}
                      strokeWidth={1.5}
                    />
                  )}
                  <step.Icon
                    className={cn(
                      "h-3.5 w-3.5 shrink-0 hidden xs:block",
                      isDone ? "text-ink-500" : isCurrent ? "text-ink-700" : "text-ink-300"
                    )}
                    strokeWidth={1.5}
                  />
                  <span
                    className={cn(
                      "text-micro font-medium truncate",
                      isDone
                        ? "text-ink-400 line-through"
                        : isCurrent
                          ? "text-ink-900"
                          : "text-ink-500"
                    )}
                  >
                    {step.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <span
                    className="hidden sm:block flex-1 h-px bg-ink-100 mx-1 min-w-[8px]"
                    aria-hidden
                  />
                )}
              </li>
            );
          })}
        </ol>
      </CardBody>
    </Card>
  );
}
