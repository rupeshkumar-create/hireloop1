"use client";

import type { MyProfileData } from "@/lib/api/profile";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/utils";

type ChatContextBarProps = {
  profile: MyProfileData | null;
  matchCount: number | null;
  profileCompleteness: number | null;
  topGap?: string | null;
  onChipClick?: (message: string) => void;
  className?: string;
};

export function ChatContextBar({
  profileCompleteness,
  matchCount,
  topGap,
  onChipClick,
  className,
}: ChatContextBarProps) {
  const chips: { label: string; message: string }[] = [];

  if (profileCompleteness != null && profileCompleteness > 0) {
    chips.push({
      label: `Profile ${profileCompleteness}%`,
      message: "What should I add to improve my match quality?",
    });
  }
  if (matchCount != null && matchCount > 0) {
    chips.push({
      label: `${matchCount} matches`,
      message: "Show me my best matches right now.",
    });
  }
  if (topGap) {
    chips.push({
      label: `Add ${topGap}`,
      message: `Help me add my ${topGap} to improve match scores.`,
    });
  }

  if (chips.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap gap-1.5 px-1", className)}>
      {chips.map((chip) => (
        <button
          key={chip.label}
          type="button"
          onClick={() => onChipClick?.(chip.message)}
          className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full"
        >
          <Badge tone={chip.label.includes("Add") ? "strong" : "accent"}>{chip.label}</Badge>
        </button>
      ))}
    </div>
  );
}
