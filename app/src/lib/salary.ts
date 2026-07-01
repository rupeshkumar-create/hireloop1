import { currencyForMarket, type MarketCode } from "@/lib/markets";

export type SalaryCurrency = "INR" | "USD" | "GBP";

/** Map market or ISO currency code to a supported salary currency. */
export function resolveSalaryCurrency(
  marketOrCurrency?: string | null,
): SalaryCurrency {
  const raw = (marketOrCurrency ?? "IN").toUpperCase();
  if (raw === "USD" || raw === "US") return "USD";
  if (raw === "GBP" || raw === "GB") return "GBP";
  if (raw === "INR" || raw === "IN") return "INR";
  return currencyForMarket(raw) as SalaryCurrency;
}

const LOCALE_FOR_CURRENCY: Record<SalaryCurrency, string> = {
  INR: "en-IN",
  USD: "en-US",
  GBP: "en-GB",
};

function formatAnnualAmount(amount: number, currency: SalaryCurrency): string {
  return new Intl.NumberFormat(LOCALE_FOR_CURRENCY[currency], {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format a job or profile salary range for display.
 *
 * INR amounts are stored as annual rupees (LPA × 100_000).
 * USD/GBP amounts are stored as annual whole currency units.
 */
export function formatSalaryRange(
  min: number | null | undefined,
  max: number | null | undefined,
  opts?: { market?: string | null; currency?: string | null },
): string | null {
  const lo = min ?? null;
  const hi = max ?? null;
  if (lo == null && hi == null) return null;

  const currency = resolveSalaryCurrency(opts?.currency ?? opts?.market ?? "IN");

  if (currency === "INR") {
    const toLpa = (n: number) => Math.round(n / 100_000);
    if (lo != null && hi != null) return `${toLpa(lo)}–${toLpa(hi)} LPA`;
    if (lo != null) return `${toLpa(lo)}+ LPA`;
    if (hi != null) return `Up to ${toLpa(hi)} LPA`;
    return null;
  }

  if (lo != null && hi != null) {
    return `${formatAnnualAmount(lo, currency)}–${formatAnnualAmount(hi, currency)}`;
  }
  if (lo != null) return `${formatAnnualAmount(lo, currency)}+`;
  if (hi != null) return `Up to ${formatAnnualAmount(hi, currency)}`;
  return null;
}

/** Format a single stored compensation amount for display. */
export function formatCompensationAmount(
  amount: number | null | undefined,
  opts?: { market?: string | null; currency?: string | null },
): string | null {
  if (amount == null) return null;
  return formatSalaryRange(amount, amount, opts);
}

/** Recruiter role form labels for comp min/max fields. */
export function compFieldLabel(
  market: MarketCode,
  which: "min" | "max",
): string {
  if (market === "US") {
    return which === "min" ? "Comp min (USD k/yr)" : "Comp max (USD k/yr)";
  }
  if (market === "GB") {
    return which === "min" ? "Comp min (GBP k/yr)" : "Comp max (GBP k/yr)";
  }
  return which === "min" ? "Comp min (LPA)" : "Comp max (LPA)";
}

/** Label for profile salary inputs (onboarding / completion forms). */
export function salaryInputLabel(market: MarketCode): string {
  if (market === "US") return "Expected salary (USD/yr)";
  if (market === "GB") return "Expected salary (GBP/yr)";
  return "Expected CTC (LPA)";
}

export function salaryInputHint(market: MarketCode): string {
  if (market === "US") return "Annual salary in US dollars (e.g. 120 for $120k).";
  if (market === "GB") return "Annual salary in pounds (e.g. 65 for £65k).";
  return "In LPA (lakhs per annum).";
}

export function salaryInputSuffix(market: MarketCode): string {
  if (market === "US") return "k USD";
  if (market === "GB") return "k GBP";
  return "LPA";
}

/** Convert profile form input to DB storage units. */
export function profileSalaryToStorage(
  raw: string | number | undefined,
  market: MarketCode,
): number | undefined {
  if (raw === undefined || raw === "") return undefined;
  const n = typeof raw === "number" ? raw : Number.parseFloat(String(raw));
  if (!Number.isFinite(n) || n <= 0) return undefined;
  if (market === "IN") return Math.round(n * 100_000);
  // US/GB forms accept thousands (120 → $120k)
  return Math.round(n * 1_000);
}

/** Convert stored salary to form display units. */
export function profileSalaryFromStorage(
  stored: number | null | undefined,
  market: MarketCode,
): string {
  if (stored == null || stored <= 0) return "";
  if (market === "IN") return String(Math.round(stored / 100_000));
  return String(Math.round(stored / 1_000));
}
