import { currencyForMarket, type MarketCode, type SalaryCurrency } from "@/lib/markets";

export type { SalaryCurrency };

/** India-only marketplace — always INR. */
export function resolveSalaryCurrency(
  _marketOrCurrency?: string | null,
): SalaryCurrency {
  return currencyForMarket("IN");
}

const LOCALE_FOR_CURRENCY: Record<SalaryCurrency, string> = {
  INR: "en-IN",
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
 */
export function formatSalaryRange(
  min: number | null | undefined,
  max: number | null | undefined,
  _opts?: { market?: string | null; currency?: string | null },
): string | null {
  const lo = min ?? null;
  const hi = max ?? null;
  if (lo == null && hi == null) return null;

  const toLpa = (n: number) => Math.round(n / 100_000);
  if (lo != null && hi != null) return `${toLpa(lo)}–${toLpa(hi)} LPA`;
  if (lo != null) return `${toLpa(lo)}+ LPA`;
  if (hi != null) return `Up to ${toLpa(hi)} LPA`;
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
export function compFieldLabel(_market: MarketCode, which: "min" | "max"): string {
  return which === "min" ? "Comp min (LPA)" : "Comp max (LPA)";
}

/** Label for profile salary inputs (onboarding / completion forms). */
export function salaryInputLabel(_market: MarketCode): string {
  return "Expected CTC (LPA)";
}

export function salaryInputHint(_market: MarketCode): string {
  return "In LPA (lakhs per annum).";
}

export function salaryInputSuffix(_market: MarketCode): string {
  return "LPA";
}

/** Convert profile form input (LPA) to DB storage units (annual rupees). */
export function profileSalaryToStorage(
  raw: string | number | undefined,
  _market: MarketCode,
): number | undefined {
  if (raw === undefined || raw === "") return undefined;
  const n = typeof raw === "number" ? raw : Number.parseFloat(String(raw));
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.round(n * 100_000);
}

/** Convert stored salary (annual rupees) to form display units (LPA). */
export function profileSalaryFromStorage(
  stored: number | null | undefined,
  _market: MarketCode,
): string {
  if (stored == null || stored <= 0) return "";
  return String(Math.round(stored / 100_000));
}

/** Kept for callers that previously formatted non-INR annual amounts. */
export function formatLegacyAnnual(
  amount: number,
  currency: SalaryCurrency = "INR",
): string {
  return formatAnnualAmount(amount, currency);
}
