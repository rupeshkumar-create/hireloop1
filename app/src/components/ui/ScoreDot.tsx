/**
 * ScoreDot — the ONLY decorative number treatment in the app.
 *
 *   <ScoreDot value={0.82} />        // → ● 82%
 *   <ScoreDot value={42} label="match" /> // → ● 42% match
 *
 * Accepts either 0–1 (float) or 0–100 (int). No traffic-light colours.
 * The accent dot + the number do all the work (DESIGN.md §7.5).
 */

import { cn } from "@/lib/utils";

export function ScoreDot({
  value,
  label,
  size = "md",
  className,
}: {
  value: number;
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const pct = Math.round(value > 1 ? value : value * 100);

  const dotSize = size === "lg" ? "w-2 h-2" : size === "sm" ? "w-1 h-1" : "w-1.5 h-1.5";
  const textSize =
    size === "lg" ? "text-h3" : size === "sm" ? "text-micro" : "text-small";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-medium text-ink-900",
        textSize,
        className
      )}
    >
      <span
        className={cn("rounded-full bg-accent shrink-0", dotSize)}
        aria-hidden
      />
      {pct}%{label && <span className="text-ink-500 font-normal ml-0.5">{label}</span>}
    </span>
  );
}
