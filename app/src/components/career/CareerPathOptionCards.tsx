"use client";

/**
 * CareerPathOptionCards — top 3 career paths as compact selectable rows.
 * Used in chat empty state and home panel before job results.
 */

import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, Route, Sparkles } from "lucide-react";
import {
  fetchCareerPath,
  generateCareerPath,
  prioritizeCareerPath,
  type CareerPath,
  type CareerStep,
} from "@/lib/api/career";
import { cn } from "@/lib/utils";
import { Button, Card, CardBody } from "@/components/ui";

export type CareerPathOption = {
  id: string;
  title: string;
  rationale: string;
  skillsToBuild: string[];
  timeframe: string | null;
};

function stepsToOptions(path: CareerPath): CareerPathOption[] {
  const nextSteps = path.steps.filter(
    (s) => s.level === "next" || s.level === "future"
  );
  const source: CareerStep[] =
    nextSteps.length > 0
      ? nextSteps.slice(0, 3)
      : path.target_titles.slice(0, 3).map((title) => ({
          title,
          level: "next",
          timeframe: null,
          rationale: path.summary,
          skills_to_build: [],
        }));

  return source.map((s, i) => ({
    id: `${path.id}-${i}`,
    title: s.title,
    rationale:
      s.rationale?.trim() ||
      `A strong next move based on your background toward ${s.title}.`,
    skillsToBuild: s.skills_to_build ?? [],
    timeframe: s.timeframe,
  }));
}

type Props = {
  onSelectPath: (option: CareerPathOption) => void;
  onPathsReady?: (count: number) => void;
  className?: string;
  compact?: boolean;
};

export function CareerPathOptionCards({
  onSelectPath,
  onPathsReady,
  className,
  compact = false,
}: Props) {
  const [options, setOptions] = useState<CareerPathOption[]>([]);
  const [prioritizedTitle, setPrioritizedTitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      let path = await fetchCareerPath();
      if (!path) {
        setGenerating(true);
        try {
          path = await generateCareerPath();
        } finally {
          setGenerating(false);
        }
      }
      const opts = path ? stepsToOptions(path) : [];
      setOptions(opts);
      if (path?.prioritized_title) {
        setPrioritizedTitle(path.prioritized_title);
        const match = opts.find(
          (o) =>
            o.title.toLowerCase() === path!.prioritized_title!.toLowerCase()
        );
        if (match) setSelectedId(match.id);
      }
      onPathsReady?.(opts.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load career paths");
      onPathsReady?.(0);
    } finally {
      setLoading(false);
    }
  }, [onPathsReady]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSelect(opt: CareerPathOption) {
    if (savingId) return;
    setSelectedId(opt.id);
    setSavingId(opt.id);
    setError(null);
    try {
      const path = await prioritizeCareerPath(opt.title);
      setPrioritizedTitle(path.prioritized_title ?? opt.title);
      onSelectPath(opt);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your choice");
      setSelectedId(null);
    } finally {
      setSavingId(null);
    }
  }

  if (loading || generating) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 text-small text-ink-500 py-3",
          className
        )}
      >
        <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
        {generating ? "Aarya is mapping your career paths…" : "Loading paths…"}
      </div>
    );
  }

  if (error && !options.length) {
    return (
      <Card className={className}>
        <CardBody className="space-y-2">
          <p className="text-small text-destructive">{error}</p>
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Try again
          </Button>
        </CardBody>
      </Card>
    );
  }

  if (!options.length) return null;

  return (
    <div className={cn("space-y-2", className)}>
      {!compact && (
        <div className="flex items-center gap-2">
          <Route className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
          <p className="text-small font-semibold text-ink-900">
            Top career paths for you
          </p>
        </div>
      )}
      <p className="text-micro text-ink-500">
        {prioritizedTitle
          ? `Prioritizing ${prioritizedTitle} — job search stays aligned to this path.`
          : "Pick one to prioritize — Aarya will search jobs aligned to that path."}
      </p>
      {error && (
        <p className="text-micro text-destructive">{error}</p>
      )}
      <div className="space-y-1.5" role="listbox" aria-label="Career path options">
        {options.map((opt, i) => {
          const isSelected =
            selectedId === opt.id ||
            (prioritizedTitle?.toLowerCase() === opt.title.toLowerCase());
          const isSaving = savingId === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              role="option"
              aria-selected={isSelected}
              disabled={Boolean(savingId)}
              onClick={() => void handleSelect(opt)}
              className={cn(
                "w-full text-left rounded-lg border px-3 py-2.5 transition-colors duration-fast",
                "hover:bg-ink-50 hover:border-ink-300",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-900 focus-visible:ring-offset-2",
                "disabled:opacity-60 disabled:cursor-wait",
                isSelected
                  ? "border-ink-900 bg-ink-50 ring-1 ring-ink-900/10"
                  : "border-ink-200 bg-paper-1"
              )}
            >
              <div className="flex items-start gap-2.5">
                <span
                  className={cn(
                    "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border-2 text-[10px] font-bold",
                    isSelected
                      ? "border-ink-900 bg-ink-900 text-paper-0"
                      : "border-ink-300 bg-paper-0 text-ink-400"
                  )}
                >
                  {isSaving ? (
                    <Loader2 className="h-2.5 w-2.5 animate-spin" />
                  ) : isSelected ? (
                    <Check className="h-2.5 w-2.5" strokeWidth={3} />
                  ) : (
                    i + 1
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-small font-medium text-ink-900 leading-snug">
                    {opt.title}
                  </p>
                  <p className="text-micro text-ink-500 line-clamp-2 mt-0.5">
                    {opt.rationale}
                  </p>
                  {opt.timeframe && (
                    <p className="text-micro text-ink-400 mt-1">{opt.timeframe}</p>
                  )}
                  {opt.skillsToBuild.length > 0 && (
                    <p className="text-micro text-ink-400 mt-1 truncate">
                      Skills to build: {opt.skillsToBuild.slice(0, 3).join(", ")}
                    </p>
                  )}
                </div>
                {i === 0 && !isSelected && (
                  <Sparkles
                    className="h-3.5 w-3.5 text-accent shrink-0 mt-0.5"
                    strokeWidth={1.5}
                    aria-label="Recommended"
                  />
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
