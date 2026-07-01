"""
Multi-region marketplace constants and SQL helpers.

Replaces the former India-only (R4) hard lock with per-user `market` scoping.
"""

from __future__ import annotations

import re

SUPPORTED_MARKETS: frozenset[str] = frozenset({"IN", "US", "GB"})
DEFAULT_MARKET = "IN"

MARKET_CURRENCIES: dict[str, str] = {
    "IN": "INR",
    "US": "USD",
    "GB": "GBP",
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
}

MARKET_LABELS: dict[str, str] = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
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
    ("united states", "US"),
    ("usa", "US"),
    (" u.s.", "US"),
    ("united kingdom", "GB"),
    ("england", "GB"),
    ("scotland", "GB"),
    ("wales", "GB"),
    ("london", "GB"),
    ("manchester", "GB"),
)

_US_STATE_RE = re.compile(r",\s*([A-Z]{2})\s*(?:,|$)")
_GB_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})\b", re.I)


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
    return {"IN": "+91", "US": "+1", "GB": "+44"}.get(normalize_market(market), "+91")


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

    if m == "US":
        if p.startswith("+1"):
            digits = p[2:]
        elif p.startswith("1") and len(p) == 11:
            digits = p[1:]
        else:
            raise ValueError("US numbers must start with +1")
        if not digits.isdigit() or len(digits) != 10:
            raise ValueError("Invalid US phone number")
        return f"+1{digits}"

    if m == "GB":
        if not p.startswith("+44"):
            raise ValueError("UK numbers must start with +44")
        digits = p[3:]
        if not digits.isdigit() or len(digits) < 10 or len(digits) > 11:
            raise ValueError("Invalid UK phone number")
        return f"+44{digits}"

    raise ValueError(f"Unsupported market: {m}")
