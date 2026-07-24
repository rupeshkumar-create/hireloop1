"use client";

import { cn } from "@/lib/utils";

const BAR_COUNT = 5;

export function ComposerWaveform({
  level,
  active,
  mode,
  className,
}: {
  level: number;
  active: boolean;
  mode: "listening" | "speaking";
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(1, level));
  const label = mode === "listening" ? "Listening level" : "Speaking level";

  return (
    <div
      role="img"
      aria-label={active ? label : undefined}
      aria-hidden={active ? undefined : true}
      className={cn(
        "flex h-4 items-end gap-0.5",
        !active && "opacity-0",
        className,
      )}
    >
      {Array.from({ length: BAR_COUNT }, (_, i) => {
        const peak = Math.max(0.15, clamped * (0.55 + ((i % 3) + 1) * 0.15));
        return (
          <span
            key={i}
            className={cn(
              "w-0.5 rounded-sm bg-ink-700 transition-[height] duration-75",
              mode === "speaking" && "bg-accent",
            )}
            style={{ height: `${Math.round(peak * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
