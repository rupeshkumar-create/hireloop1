export type MarketCode = "IN" | "US" | "GB";

export type MarketConfig = {
  code: MarketCode;
  label: string;
  dial: string;
  placeholder: string;
  helper: string;
  validateNational: (digits: string) => boolean;
  toE164: (digits: string) => string;
};

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
  {
    code: "US",
    label: "United States",
    dial: "+1",
    placeholder: "415 555 0100",
    helper: "10-digit US mobile number.",
    validateNational: (d) => /^\d{10}$/.test(d),
    toE164: (d) => `+1${d}`,
  },
  {
    code: "GB",
    label: "United Kingdom",
    dial: "+44",
    placeholder: "7911 123456",
    helper: "10–11 digit UK mobile number.",
    validateNational: (d) => /^\d{10,11}$/.test(d),
    toE164: (d) => `+44${d}`,
  },
];

export function marketByCode(code: string): MarketConfig {
  return SUPPORTED_MARKETS.find((m) => m.code === code) ?? SUPPORTED_MARKETS[0];
}

const MARKET_CURRENCY_MAP: Record<MarketCode, "INR" | "USD" | "GBP"> = {
  IN: "INR",
  US: "USD",
  GB: "GBP",
};

export function currencyForMarket(code: string): "INR" | "USD" | "GBP" {
  return MARKET_CURRENCY_MAP[code as MarketCode] ?? "INR";
}
