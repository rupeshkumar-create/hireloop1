import type { MatchedJob } from "@/lib/api/matches";
import { resolveSalaryCurrency, type SalaryCurrency } from "@/lib/salary";

export type JobCardFilters = {
  remoteOnly?: boolean;
  /** Minimum salary in display units (LPA for INR, thousands for USD/GBP). */
  minSalary?: number;
  minSalaryCurrency?: SalaryCurrency;
};

/** Parse in-chat filter intents like "only remote" or "above 20 LPA" / "$120k". */
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

  const usdMatch = t.match(
    /(?:above|over|at least|minimum|min)\s*\$?\s*(\d+(?:\.\d+)?)\s*k?(?:\s*usd|\s*\$)?/,
  );
  if (!filters.minSalary && usdMatch && (t.includes("$") || t.includes("usd"))) {
    filters.minSalary = Number(usdMatch[1]);
    filters.minSalaryCurrency = "USD";
  }

  const gbpMatch = t.match(
    /(?:above|over|at least|minimum|min)\s*£?\s*(\d+(?:\.\d+)?)\s*k?(?:\s*gbp|\s*£)?/,
  );
  if (!filters.minSalary && gbpMatch && (t.includes("£") || t.includes("gbp"))) {
    filters.minSalary = Number(gbpMatch[1]);
    filters.minSalaryCurrency = "GBP";
  }

  return filters;
}

function minSalaryToStorage(
  minSalary: number,
  currency: SalaryCurrency,
): number {
  if (currency === "INR") return Math.round(minSalary * 100_000);
  return Math.round(minSalary * 1_000);
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
    const filterCurrency = filters.minSalaryCurrency;
    out = out.filter((j) => {
      const jobCurrency = resolveSalaryCurrency(j.salary_currency ?? "IN");
      if (jobCurrency !== filterCurrency) return true;
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
    if (filters.minSalaryCurrency === "INR") {
      parts.push(`≥ ${filters.minSalary} LPA`);
    } else if (filters.minSalaryCurrency === "USD") {
      parts.push(`≥ $${filters.minSalary}k`);
    } else {
      parts.push(`≥ £${filters.minSalary}k`);
    }
  }
  return parts.length ? parts.join(" · ") : null;
}
