"""
India-only marketplace constants and SQL helpers.

Hireschema MVP is locked to Indian candidates and Indian recruiters.
`market` remains on user/candidate/job rows for schema compatibility, but
only `IN` is supported. Non-IN values are normalised to `IN`.
"""

from __future__ import annotations

# ISO 3166-1 alpha-2 — India only for MVP.
SUPPORTED_MARKETS: frozenset[str] = frozenset({"IN"})
DEFAULT_MARKET = "IN"

# Used as the default ENABLED_MARKETS value.
ALL_SUPPORTED_MARKET_CODES: tuple[str, ...] = ("IN",)

MARKET_CURRENCIES: dict[str, str] = {
    "IN": "INR",
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
}

MARKET_LABELS: dict[str, str] = {
    "IN": "India",
}

# Location substring → ISO market (India only). First match wins.
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
    ("maharashtra", "IN"),
    ("telangana", "IN"),
    ("tamil nadu", "IN"),
    ("new delhi", "IN"),
)


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
    """Return a supported market code; always fall back to IN."""
    raw = (code or DEFAULT_MARKET).upper().strip()
    allowed = enabled or SUPPORTED_MARKETS
    if raw in allowed:
        return raw
    return DEFAULT_MARKET


def currency_for_market(market: str) -> str:
    return MARKET_CURRENCIES.get(normalize_market(market), "INR")


def resolve_country_from_location(location: str) -> str | None:
    """Best-effort India market from free-text location. Non-India → None."""
    if not location:
        return None
    low = f" {location.lower()} "
    for hint, market in _LOCATION_MARKET_HINTS:
        if hint in low:
            return market
    return None


def scrape_locations_for_market(market: str, *, city_hint: str | None = None) -> list[str]:
    """
    Ordered scrape/search locations: city first (when known), then India hubs.
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
    """E.164 country dial prefix — India only (+91)."""
    _ = normalize_market(market)
    return "+91"


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
    Validate Indian (+91) mobile numbers. Returns normalized E.164 string.
    Raises ValueError on invalid input.
    """
    _ = normalize_market(market)
    p = phone.strip().replace(" ", "").replace("-", "")

    if not p.startswith("+91"):
        raise ValueError("Indian numbers must start with +91")
    digits = p[3:]
    if not digits.isdigit() or len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("Invalid Indian mobile number")
    return f"+91{digits}"
