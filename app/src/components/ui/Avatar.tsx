/**
 * Avatar — text initial in ink-50 circle.
 *
 *   <Avatar name="Priya Sharma" />            // shows "PS"
 *   <Avatar name="Priya Sharma" src="..." />  // image fallback
 *   <Avatar size="lg" tone="dark" />          // tones: light (default) | dark | accent
 *
 * No gradients (DESIGN.md §11). No emoji. No coloured initials.
 */

import { cn } from "@/lib/utils";

type Size = "sm" | "md" | "lg";
type Tone = "light" | "dark" | "accent";

const SIZE: Record<Size, string> = {
  sm: "h-7  w-7  text-micro",
  md: "h-9  w-9  text-small",
  lg: "h-12 w-12 text-h3",
};

const TONE: Record<Tone, string> = {
  light:  "bg-ink-50 text-ink-700",
  dark:   "bg-ink-900 text-paper-0",
  accent: "bg-accent text-on-accent",
};

export function Avatar({
  name = "",
  src,
  size = "md",
  tone = "light",
  className,
}: {
  name?: string;
  src?: string | null;
  size?: Size;
  tone?: Tone;
  className?: string;
}) {
  const initials = getInitials(name);

  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name}
        className={cn(
          "rounded-full object-cover border border-ink-100 shrink-0",
          SIZE[size],
          className
        )}
      />
    );
  }

  return (
    <div
      aria-label={name || "Avatar"}
      className={cn(
        "rounded-full flex items-center justify-center font-medium shrink-0 select-none",
        SIZE[size],
        TONE[tone],
        className
      )}
    >
      {initials || "·"}
    </div>
  );
}

function getInitials(name: string): string {
  if (!name) return "";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
