"use client";

import { SUPPORTED_MARKETS, type MarketCode } from "@/lib/markets";
import { cn } from "@/lib/utils";

type MarketSelectProps = {
  id?: string;
  value: MarketCode;
  onChange: (code: MarketCode) => void;
  className?: string;
  disabled?: boolean;
};

export function MarketSelect({
  id = "home-market",
  value,
  onChange,
  className,
  disabled = false,
}: MarketSelectProps) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as MarketCode)}
      className={cn(
        "h-10 w-full rounded-md border border-ink-100 bg-paper-1 px-3 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent-ring",
        className,
      )}
    >
      {SUPPORTED_MARKETS.map((m) => (
        <option key={m.code} value={m.code}>
          {m.label}
        </option>
      ))}
    </select>
  );
}
