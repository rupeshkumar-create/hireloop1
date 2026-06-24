import type { MatchedJob } from "@/lib/api/matches";

export type JobCardFilters = {
  remoteOnly?: boolean;
  minCtcLpa?: number;
};

/** Parse in-chat filter intents like "only remote" or "above 20 LPA". */
export function parseJobFiltersFromText(text: string): JobCardFilters {
  const t = text.toLowerCase();
  const filters: JobCardFilters = {};

  if (
    /\b(only remote|remote only|wfh only|work from home only|show only remote)\b/.test(
      t
    )
  ) {
    filters.remoteOnly = true;
  }

  const lpaMatch = t.match(
    /(?:above|over|at least|minimum|min)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*lpa/
  );
  if (lpaMatch) {
    filters.minCtcLpa = Number(lpaMatch[1]);
  }

  return filters;
}

export function applyJobCardFilters(
  jobs: MatchedJob[],
  filters: JobCardFilters
): MatchedJob[] {
  let out = jobs;
  if (filters.remoteOnly) {
    out = out.filter((j) => j.is_remote);
  }
  if (filters.minCtcLpa && filters.minCtcLpa > 0) {
    const minPaise = Math.round(filters.minCtcLpa * 100_000);
    out = out.filter(
      (j) => (j.ctc_max ?? j.ctc_min ?? 0) >= minPaise || (j.ctc_min ?? 0) >= minPaise
    );
  }
  return out;
}

export function jobFiltersLabel(filters: JobCardFilters): string | null {
  const parts: string[] = [];
  if (filters.remoteOnly) parts.push("remote only");
  if (filters.minCtcLpa) parts.push(`≥ ${filters.minCtcLpa} LPA`);
  return parts.length ? parts.join(" · ") : null;
}
