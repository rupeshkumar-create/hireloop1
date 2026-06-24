"use client";

import { Brain } from "lucide-react";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/utils";

type IntelligenceHeroProps = {
  archetype?: string | null;
  nextRole?: string | null;
  completeness?: number | null;
  onOpenIntelligence?: () => void;
  onAskAarya?: (message: string) => void;
  className?: string;
};

export function IntelligenceHero({
  archetype,
  nextRole,
  completeness,
  onOpenIntelligence,
  onAskAarya,
  className,
}: IntelligenceHeroProps) {
  if (!archetype && !nextRole && completeness == null) return null;

  return (
    <div
      className={cn(
        "rounded-lg border border-ink-100 bg-paper-1 p-4 space-y-3",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink-900">
          <Brain className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
        </div>
        <div className="min-w-0 flex-1">
          {archetype && (
            <p className="text-micro uppercase tracking-wide text-ink-500">Archetype</p>
          )}
          <p className="text-h3 text-ink-900 truncate">{archetype ?? "Building your profile…"}</p>
          {nextRole && (
            <p className="text-small text-ink-500 mt-1">
              Likely next: <span className="text-ink-900">{nextRole}</span>
            </p>
          )}
        </div>
        {completeness != null && (
          <Badge tone="accent">{completeness}%</Badge>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {onOpenIntelligence && (
          <Button variant="secondary" size="sm" onClick={onOpenIntelligence}>
            View intelligence
          </Button>
        )}
        {onAskAarya && completeness != null && completeness < 85 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              onAskAarya("What are the top 3 things I should add to improve my match quality?")
            }
          >
            Improve matches
          </Button>
        )}
      </div>
    </div>
  );
}

export function ProfileGapList({
  gaps,
  onFix,
}: {
  gaps: string[];
  onFix?: (gap: string) => void;
}) {
  if (gaps.length === 0) return null;
  return (
    <ul className="space-y-2">
      {gaps.slice(0, 3).map((gap, i) => (
        <li
          key={gap}
          className="flex items-center justify-between gap-2 rounded-md border border-ink-100 px-3 py-2"
        >
          <span className="text-small text-ink-700">
            <span className="text-ink-400 mr-2">{i + 1}.</span>
            {gap}
          </span>
          {onFix && (
            <button
              type="button"
              onClick={() => onFix(gap)}
              className="text-micro font-medium text-accent hover:underline shrink-0"
            >
              Fix
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
