export type MarketCode =
  | "IN"
  | "US"
  | "GB"
  | "AT"
  | "DE"
  | "FR"
  | "AE"
  | "AU"
  | "CA"
  | "CH"
  | "NL"
  | "SG";

export type MarketConfig = {
  code: MarketCode;
  label: string;
  dial: string;
  placeholder: string;
  helper: string;
  validateNational: (digits: string) => boolean;
  toE164: (digits: string) => string;
};

function genericNationalValidator(digits: string): boolean {
  return /^\d{7,12}$/.test(digits);
}

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
  {
    code: "CA",
    label: "Canada",
    dial: "+1",
    placeholder: "416 555 0100",
    helper: "10-digit Canadian mobile number.",
    validateNational: (d) => /^\d{10}$/.test(d),
    toE164: (d) => `+1${d}`,
  },
  {
    code: "AU",
    label: "Australia",
    dial: "+61",
    placeholder: "412 345 678",
    helper: "9-digit Australian mobile (without leading 0).",
    validateNational: (d) => /^[45]\d{8}$/.test(d),
    toE164: (d) => `+61${d}`,
  },
  {
    code: "DE",
    label: "Germany",
    dial: "+49",
    placeholder: "151 23456789",
    helper: "10–11 digit German mobile (without leading 0).",
    validateNational: genericNationalValidator,
    toE164: (d) => `+49${d}`,
  },
  {
    code: "FR",
    label: "France",
    dial: "+33",
    placeholder: "6 12 34 56 78",
    helper: "9-digit French mobile (without leading 0).",
    validateNational: (d) => /^[67]\d{8}$/.test(d),
    toE164: (d) => `+33${d}`,
  },
  {
    code: "NL",
    label: "Netherlands",
    dial: "+31",
    placeholder: "6 12345678",
    helper: "9-digit Dutch mobile (without leading 0).",
    validateNational: (d) => /^6\d{8}$/.test(d),
    toE164: (d) => `+31${d}`,
  },
  {
    code: "AT",
    label: "Austria",
    dial: "+43",
    placeholder: "664 1234567",
    helper: "9–11 digit Austrian mobile (without leading 0).",
    validateNational: genericNationalValidator,
    toE164: (d) => `+43${d}`,
  },
  {
    code: "CH",
    label: "Switzerland",
    dial: "+41",
    placeholder: "79 123 45 67",
    helper: "9-digit Swiss mobile (without leading 0).",
    validateNational: (d) => /^7[5-9]\d{7}$/.test(d),
    toE164: (d) => `+41${d}`,
  },
  {
    code: "AE",
    label: "United Arab Emirates",
    dial: "+971",
    placeholder: "50 123 4567",
    helper: "9-digit UAE mobile (without leading 0).",
    validateNational: (d) => /^5\d{8}$/.test(d),
    toE164: (d) => `+971${d}`,
  },
  {
    code: "SG",
    label: "Singapore",
    dial: "+65",
    placeholder: "8123 4567",
    helper: "8-digit Singapore mobile.",
    validateNational: (d) => /^[89]\d{7}$/.test(d),
    toE164: (d) => `+65${d}`,
  },
];

export function marketByCode(code: string): MarketConfig {
  return SUPPORTED_MARKETS.find((m) => m.code === code) ?? SUPPORTED_MARKETS[0];
}

export type SalaryCurrency =
  | "INR"
  | "USD"
  | "GBP"
  | "EUR"
  | "AUD"
  | "CAD"
  | "CHF"
  | "AED"
  | "SGD";

const MARKET_CURRENCY_MAP: Record<MarketCode, SalaryCurrency> = {
  IN: "INR",
  US: "USD",
  GB: "GBP",
  AT: "EUR",
  DE: "EUR",
  FR: "EUR",
  NL: "EUR",
  CH: "CHF",
  AE: "AED",
  AU: "AUD",
  CA: "CAD",
  SG: "SGD",
};

export function currencyForMarket(code: string): SalaryCurrency {
  return MARKET_CURRENCY_MAP[code as MarketCode] ?? "INR";
}

/** Dial prefix hint for settings copy (unique prefixes only). */
export function marketDialSummary(): string {
  const dials = [...new Set(SUPPORTED_MARKETS.map((m) => m.dial))].sort();
  return dials.join(" · ");
}
