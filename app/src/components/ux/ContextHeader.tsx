"use client";

import { MapPin, Sparkles } from "@/components/brand/icons";
import { ScoreDot } from "@/components/ui";
import { cn } from "@/lib/utils";

type ContextHeaderProps = {
  name?: string | null;
  location?: string | null;
  profileCompleteness?: number | null;
  matchCount?: number | null;
  className?: string;
};

export function ContextHeader({
  name,
  location,
  profileCompleteness,
  matchCount,
  className,
}: ContextHeaderProps) {
  const parts: string[] = [];
  if (name) parts.push(name.split(" ")[0] ?? name);
  if (location) parts.push(location);
  if (profileCompleteness != null && profileCompleteness > 0) {
    parts.push(`${profileCompleteness}% profile`);
  }
  if (matchCount != null && matchCount > 0) {
    parts.push(`${matchCount} matches`);
  }
  if (parts.length === 0) return null;

  return (
    <div
      className={cn(
        "flex items-center gap-2 border-b border-ink-100 bg-paper-1 px-4 py-2 text-micro text-ink-500",
        className,
      )}
    >
      <Sparkles className="h-3.5 w-3.5 shrink-0 text-ink-400" strokeWidth={1.5} />
      <span className="truncate">{parts.join(" · ")}</span>
      {profileCompleteness != null && profileCompleteness > 0 && (
        <ScoreDot value={profileCompleteness} size="sm" className="ml-auto hidden sm:inline-flex" />
      )}
      {location && (
        <MapPin className="h-3 w-3 shrink-0 text-ink-300 sm:hidden" strokeWidth={1.5} />
      )}
    </div>
  );
}
