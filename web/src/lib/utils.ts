import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes without conflicts.
 * Usage: cn("px-4 py-2", condition && "bg-ink-500", className)
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a number as Indian Rupees.
 * e.g. formatINR(1500000) → "₹15,00,000"
 */
export function formatINR(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format a salary range in LPA (Lakhs Per Annum).
 * e.g. formatLPA(1200000, 1800000) → "12–18 LPA"
 */
export function formatLPA(min: number, max: number): string {
  const toL = (n: number) => Math.round(n / 100000);
  return `${toL(min)}–${toL(max)} LPA`;
}

/**
 * Truncate a string to a max length with ellipsis.
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}

/**
 * Sleep for n milliseconds (use only in non-production / tests).
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
