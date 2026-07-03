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
  muted:  "bg-ink-100 text-ink-800 border-ink-200",
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
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border",
        "text-micro font-medium uppercase tracking-wide",
        TONE[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
