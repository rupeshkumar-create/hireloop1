import type { MatchedJob } from "@/lib/api/matches";
import type { SalaryCurrency } from "@/lib/salary";

export type JobCardFilters = {
  remoteOnly?: boolean;
  /** Minimum salary in LPA (India-only). */
  minSalary?: number;
  minSalaryCurrency?: SalaryCurrency;
};

/** Parse in-chat filter intents like "only remote" or "above 20 LPA". */
export function parseJobFiltersFromText(text: string): JobCardFilters {
  const t = text.toLowerCase();
  const filters: JobCardFilters = {};

  if (
    /\b(only remote|remote only|wfh only|work from home only|show only remote)\b/.test(
      t,
    )
  ) {
    filters.remoteOnly = true;
  }

  const lpaMatch = t.match(
    /(?:above|over|at least|minimum|min)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*lpa/,
  );
  if (lpaMatch) {
    filters.minSalary = Number(lpaMatch[1]);
    filters.minSalaryCurrency = "INR";
  }

  return filters;
}

function minSalaryToStorage(minSalary: number, _currency: SalaryCurrency): number {
  return Math.round(minSalary * 100_000);
}

export function applyJobCardFilters(
  jobs: MatchedJob[],
  filters: JobCardFilters,
): MatchedJob[] {
  let out = jobs;
  if (filters.remoteOnly) {
    out = out.filter((j) => j.is_remote);
  }
  if (filters.minSalary && filters.minSalary > 0 && filters.minSalaryCurrency) {
    const floor = minSalaryToStorage(
      filters.minSalary,
      filters.minSalaryCurrency,
    );
    out = out.filter((j) => {
      const comp = j.ctc_max ?? j.ctc_min ?? 0;
      return comp >= floor || (j.ctc_min ?? 0) >= floor;
    });
  }
  return out;
}

export function jobFiltersLabel(filters: JobCardFilters): string | null {
  const parts: string[] = [];
  if (filters.remoteOnly) parts.push("remote only");
  if (filters.minSalary && filters.minSalaryCurrency) {
    parts.push(`≥ ${filters.minSalary} LPA`);
  }
  return parts.length ? parts.join(" · ") : null;
}
