export type MarketCode = "IN";

export type MarketConfig = {
  code: MarketCode;
  label: string;
  dial: string;
  placeholder: string;
  helper: string;
  validateNational: (digits: string) => boolean;
  toE164: (digits: string) => string;
};

/** India-only marketplace — single supported home market. */
export const SUPPORTED_MARKETS: MarketConfig[] = [
  {
    code: "IN",
    label: "India",
    dial: "+91",
    placeholder: "98765 43210",
    helper: "10 digits starting with 6–9.",
    validateNational: (d) => /^[6-9]\d{9}$/.test(d),
    toE164: (d) => `+91${d}`,
  },
];

export const DEFAULT_MARKET: MarketCode = "IN";

export function marketByCode(code: string): MarketConfig {
  return SUPPORTED_MARKETS.find((m) => m.code === code) ?? SUPPORTED_MARKETS[0];
}

export type SalaryCurrency = "INR";

const MARKET_CURRENCY_MAP: Record<MarketCode, SalaryCurrency> = {
  IN: "INR",
};

export function currencyForMarket(code: string): SalaryCurrency {
  return MARKET_CURRENCY_MAP[code as MarketCode] ?? "INR";
}

/** Dial prefix hint for settings copy. */
export function marketDialSummary(): string {
  return "+91";
}
