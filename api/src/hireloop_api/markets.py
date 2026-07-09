"""
Multi-region marketplace constants and SQL helpers.

Replaces the former India-only (R4) hard lock with per-user `market` scoping.
"""

from __future__ import annotations

import re

# ISO 3166-1 alpha-2 markets we actively support for job visibility + currency.
SUPPORTED_MARKETS: frozenset[str] = frozenset(
    {
        "IN",
        "US",
        "GB",
        "AT",  # Austria
        "DE",  # Germany
        "FR",  # France
        "AE",  # UAE
        "AU",  # Australia
        "CA",  # Canada
        "CH",  # Switzerland
        "NL",  # Netherlands
        "SG",  # Singapore
    }
)
DEFAULT_MARKET = "IN"

# All actively supported markets — used as the default ENABLED_MARKETS value.
ALL_SUPPORTED_MARKET_CODES: tuple[str, ...] = tuple(sorted(SUPPORTED_MARKETS))

MARKET_CURRENCIES: dict[str, str] = {
    "IN": "INR",
    "US": "USD",
    "GB": "GBP",
    "AT": "EUR",
    "DE": "EUR",
    "FR": "EUR",
    "NL": "EUR",
    "CH": "CHF",
    "AE": "AED",
    "AU": "AUD",
    "CA": "CAD",
    "SG": "SGD",
}

MARKET_SCRAPE_LOCATIONS: dict[str, list[str]] = {
    "IN": [
        "Bengaluru, Karnataka, India",
        "Mumbai, Maharashtra, India",
        "Hyderabad, Telangana, India",
        "Delhi, India",
        "Pune, Maharashtra, India",
        "Chennai, Tamil Nadu, India",
        "Gurugram, Haryana, India",
        "Noida, Uttar Pradesh, India",
        "Kolkata, West Bengal, India",
        "Ahmedabad, Gujarat, India",
        "India",
    ],
    "US": [
        "San Francisco, California, United States",
        "New York, New York, United States",
        "Austin, Texas, United States",
        "Seattle, Washington, United States",
        "Boston, Massachusetts, United States",
        "United States",
    ],
    "GB": [
        "London, England, United Kingdom",
        "Manchester, England, United Kingdom",
        "Birmingham, England, United Kingdom",
        "United Kingdom",
    ],
    "AT": [
        "Vienna, Austria",
        "Graz, Austria",
        "Salzburg, Austria",
        "Austria",
    ],
    "DE": [
        "Berlin, Germany",
        "Munich, Germany",
        "Frankfurt, Germany",
        "Hamburg, Germany",
        "Germany",
    ],
    "FR": [
        "Paris, France",
        "Lyon, France",
        "Marseille, France",
        "France",
    ],
    "AE": [
        "Dubai, United Arab Emirates",
        "Abu Dhabi, United Arab Emirates",
        "United Arab Emirates",
    ],
    "AU": [
        "Sydney, New South Wales, Australia",
        "Melbourne, Victoria, Australia",
        "Australia",
    ],
    "CA": [
        "Toronto, Ontario, Canada",
        "Vancouver, British Columbia, Canada",
        "Canada",
    ],
    "CH": [
        "Zurich, Switzerland",
        "Geneva, Switzerland",
        "Switzerland",
    ],
    "NL": [
        "Amsterdam, Netherlands",
        "Rotterdam, Netherlands",
        "Netherlands",
    ],
    "SG": [
        "Singapore",
    ],
}

MARKET_LABELS: dict[str, str] = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "AT": "Austria",
    "DE": "Germany",
    "FR": "France",
    "AE": "United Arab Emirates",
    "AU": "Australia",
    "CA": "Canada",
    "CH": "Switzerland",
    "NL": "Netherlands",
    "SG": "Singapore",
}

# Location substring → ISO market (first match wins).
_LOCATION_MARKET_HINTS: tuple[tuple[str, str], ...] = (
    ("india", "IN"),
    ("bengaluru", "IN"),
    ("bangalore", "IN"),
    ("mumbai", "IN"),
    ("hyderabad", "IN"),
    ("delhi", "IN"),
    ("gurugram", "IN"),
    ("gurgaon", "IN"),
    ("noida", "IN"),
    ("pune", "IN"),
    ("chennai", "IN"),
    ("kolkata", "IN"),
    ("ahmedabad", "IN"),
    ("ranchi", "IN"),
    ("bokaro", "IN"),
    ("jharkhand", "IN"),
    ("karnataka", "IN"),
    ("new delhi", "IN"),
    ("united states", "US"),
    ("usa", "US"),
    (" u.s.", "US"),
    ("san francisco", "US"),
    ("brooklyn", "US"),
    ("new york", "US"),
    ("california", "US"),
    ("united kingdom", "GB"),
    ("england", "GB"),
    ("scotland", "GB"),
    ("wales", "GB"),
    ("london", "GB"),
    ("manchester", "GB"),
    ("austria", "AT"),
    ("vienna", "AT"),
    ("wien", "AT"),
    ("germany", "DE"),
    ("berlin", "DE"),
    ("munich", "DE"),
    ("france", "FR"),
    ("paris", "FR"),
    ("dubai", "AE"),
    ("abu dhabi", "AE"),
    ("uae", "AE"),
    ("united arab emirates", "AE"),
    ("australia", "AU"),
    ("sydney", "AU"),
    ("melbourne", "AU"),
    ("canada", "CA"),
    ("toronto", "CA"),
    ("vancouver", "CA"),
    ("switzerland", "CH"),
    ("zurich", "CH"),
    ("geneva", "CH"),
    ("netherlands", "NL"),
    ("amsterdam", "NL"),
    ("singapore", "SG"),
)

_US_STATE_RE = re.compile(r",\s*([A-Z]{2})\s*(?:,|$)")
_GB_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})\b", re.I)


def market_catalog() -> list[dict[str, str]]:
    """Ordered market metadata for API + admin surfaces."""
    return [
        {
            "code": code,
            "label": MARKET_LABELS[code],
            "currency": MARKET_CURRENCIES[code],
            "dial": dial_prefix_for_market(code),
        }
        for code in sorted(SUPPORTED_MARKETS)
    ]


def normalize_market(code: str | None, *, enabled: frozenset[str] | None = None) -> str:
    """Return a supported market code; fall back to IN."""
    raw = (code or DEFAULT_MARKET).upper().strip()
    allowed = enabled or SUPPORTED_MARKETS
    if raw in allowed:
        return raw
    return DEFAULT_MARKET


def currency_for_market(market: str) -> str:
    return MARKET_CURRENCIES.get(normalize_market(market), "INR")


def resolve_country_from_location(location: str) -> str | None:
    """Best-effort ISO market from free-text location."""
    if not location:
        return None
    low = f" {location.lower()} "
    for hint, market in _LOCATION_MARKET_HINTS:
        if hint in low:
            return market
    if ", us" in low or low.rstrip().endswith(" us"):
        return "US"
    if _US_STATE_RE.search(location) and "india" not in low:
        return "US"
    if _GB_POSTCODE_RE.search(location):
        return "GB"
    return None


def scrape_locations_for_market(market: str, *, city_hint: str | None = None) -> list[str]:
    """
    Ordered scrape/search locations: city first (when known), then country hubs.
    """
    m = normalize_market(market)
    base = list(MARKET_SCRAPE_LOCATIONS.get(m, MARKET_SCRAPE_LOCATIONS["IN"]))
    if not city_hint:
        return base
    hint = city_hint.strip()
    if not hint:
        return base
    if hint.lower() in {b.lower() for b in base}:
        return base
    return [hint, *base]


def job_visible_for_market_sql(*, job_alias: str = "j", market_param: str) -> str:
    """
    SQL boolean expression: job is visible to a candidate in `market_param`.

    Onsite: job.country_code must match.
    Remote: allowed_regions NULL/empty → worldwide; else must list market or WORLD.
    """
    j = job_alias
    return f"""(
        {j}.country_code = {market_param}
        OR (
            {j}.is_remote = TRUE
            AND (
                {j}.allowed_regions IS NULL
                OR cardinality({j}.allowed_regions) = 0
                OR {market_param} = ANY({j}.allowed_regions)
                OR 'WORLD' = ANY({j}.allowed_regions)
            )
        )
    )"""


def dial_prefix_for_market(market: str) -> str:
    """E.164 country dial prefix for a supported market."""
    return {
        "IN": "+91",
        "US": "+1",
        "GB": "+44",
        "AT": "+43",
        "DE": "+49",
        "FR": "+33",
        "AE": "+971",
        "AU": "+61",
        "CA": "+1",
        "CH": "+41",
        "NL": "+31",
        "SG": "+65",
    }.get(normalize_market(market), "+91")


def phone_matches_market(phone: str | None, market: str) -> bool:
    """True when phone is empty or valid E.164 for the given market."""
    if not phone or not str(phone).strip():
        return True
    try:
        validate_e164_phone(str(phone), market)
    except ValueError:
        return False
    else:
        return True


def validate_e164_phone(phone: str, market: str) -> str:
    """
    Validate phone for supported markets. Returns normalized E.164 string.
    Raises ValueError on invalid input.
    """
    m = normalize_market(market)
    p = phone.strip().replace(" ", "").replace("-", "")

    if m == "IN":
        if not p.startswith("+91"):
            raise ValueError("Indian numbers must start with +91")
        digits = p[3:]
        if not digits.isdigit() or len(digits) != 10 or digits[0] not in "6789":
            raise ValueError("Invalid Indian mobile number")
        return f"+91{digits}"

    if m in {"US", "CA"}:
        if p.startswith("+1"):
            digits = p[2:]
        elif p.startswith("1") and len(p) == 11:
            digits = p[1:]
        else:
            raise ValueError("US/CA numbers must start with +1")
        if not digits.isdigit() or len(digits) != 10:
            raise ValueError("Invalid US/CA phone number")
        return f"+1{digits}"

    if m == "GB":
        if not p.startswith("+44"):
            raise ValueError("UK numbers must start with +44")
        digits = p[3:]
        if not digits.isdigit() or len(digits) < 10 or len(digits) > 11:
            raise ValueError("Invalid UK phone number")
        return f"+44{digits}"

    # Other markets: basic E.164 length check with expected prefix when present.
    prefix = dial_prefix_for_market(m)
    if not p.startswith("+"):
        raise ValueError(f"Phone must be E.164 for market {m}")
    if prefix and not p.startswith(prefix):
        raise ValueError(f"Phone must start with {prefix} for market {m}")
    digits = re.sub(r"\D", "", p)
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Invalid phone number length")
    return f"+{digits}"
