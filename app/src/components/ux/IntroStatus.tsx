"use client";

import { Check, Circle, Clock, MessageCircle, Send } from "lucide-react";
import { cn } from "@/lib/utils";

const INTRO_STEPS = [
  { key: "pending", label: "Requested", icon: Circle },
  { key: "viewed", label: "Viewed", icon: Clock },
  { key: "accepted", label: "Accepted", icon: Check },
  { key: "sent", label: "Sent", icon: Send },
  { key: "replied", label: "Replied", icon: MessageCircle },
] as const;

function stepIndex(status: string): number {
  const order = ["pending", "invited", "viewed", "accepted", "sent", "opened", "replied"];
  const idx = order.indexOf(status);
  if (idx < 0) return 0;
  if (status === "invited") return 0;
  if (status === "opened") return 3;
  return Math.min(idx, INTRO_STEPS.length - 1);
}

export function IntroStatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    pending: "Pending",
    invited: "Invited",
    accepted: "Accepted",
    declined: "Declined",
    sent: "Sent",
    opened: "Opened",
    replied: "Replied",
    cancelled: "Cancelled",
  };
  return (
    <span className="inline-flex items-center gap-1.5 text-micro font-medium text-ink-700">
      <Circle className="h-2 w-2 fill-ink-500 text-ink-500" strokeWidth={0} />
      {labels[status] ?? status}
    </span>
  );
}

export function IntroStatusTimeline({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const current = stepIndex(status);
  return (
    <ol className={cn("flex flex-wrap gap-2", className)} aria-label="Intro progress">
      {INTRO_STEPS.map((step, i) => {
        const done = i <= current;
        const Icon = step.icon;
        return (
          <li
            key={step.key}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-micro",
              done
                ? "border-ink-900 bg-ink-50 text-ink-900"
                : "border-ink-100 text-ink-400",
            )}
          >
            <Icon className="h-3 w-3" strokeWidth={1.5} />
            {step.label}
          </li>
        );
      })}
    </ol>
  );
}
