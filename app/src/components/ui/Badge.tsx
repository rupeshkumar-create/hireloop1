/**
 * Badge — small inline tag.
 *
 *   <Badge>Remote</Badge>
 *   <Badge tone="strong">Senior</Badge>
 *   <Badge tone="accent">12 LPA</Badge>
 *
 * Two tones only: muted (default) + strong + accent. Never red/green/amber.
 * For match scores, use <ScoreDot> instead.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "muted" | "strong" | "accent";

const TONE: Record<Tone, string> = {
  muted:  "bg-ink-50 text-ink-700 border-ink-100",
  strong: "bg-ink-900 text-paper-0 border-ink-900",
  accent: "bg-accent text-accent-fg border-accent",
};

export function Badge({
  children,
  tone = "muted",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-sm border",
        "text-micro font-medium uppercase",
        TONE[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
