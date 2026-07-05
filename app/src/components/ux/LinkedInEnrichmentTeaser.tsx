"use client";

import { Loader2 } from "@/components/brand/icons";

const PLACEHOLDERS = ["Reading your headline…", "Mapping skills…", "Estimating experience…"];

export function LinkedInEnrichmentTeaser({ visible = true }: { visible?: boolean }) {
  if (!visible) return null;
  return (
    <div className="rounded-lg border border-ink-100 bg-paper-1 p-4 space-y-3 animate-pulse">
      <div className="flex items-center gap-2 text-small text-ink-700">
        <Loader2 className="h-4 w-4 animate-spin text-accent" />
        Aarya is reading your LinkedIn profile…
      </div>
      <ul className="space-y-2">
        {PLACEHOLDERS.map((line) => (
          <li key={line} className="flex items-center gap-2 text-micro text-ink-500">
            <span className="h-1.5 w-1.5 rounded-full bg-ink-300" />
            {line}
          </li>
        ))}
      </ul>
    </div>
  );
}
