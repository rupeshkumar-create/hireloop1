"""Resolve candidate salary display currency from preference + profile signals."""

from __future__ import annotations

from typing import Any

from hireloop_api.markets import currency_for_market, resolve_country_from_location

VALID_DISPLAY_CURRENCIES = frozenset({"auto", "INR", "USD", "GBP", "EUR"})


def infer_market_from_resume_location(location: str | None) -> str | None:
    if not location:
        return None
    return resolve_country_from_location(location)


def resolve_display_currency(
    preference: str | None,
    *,
    market: str = "IN",
    location_city: str | None = None,
    location_state: str | None = None,
) -> str:
    """
    Return ISO currency code for UI salary formatting.

    auto → market currency, else best-effort from resume/profile location.
    """
    pref = (preference or "auto").upper().strip()
    if pref in {"INR", "USD", "GBP", "EUR"}:
        return pref
    loc_market = infer_market_from_resume_location(
        " ".join(p for p in (location_city, location_state) if p)
    )
    if loc_market:
        return currency_for_market(loc_market)
    return currency_for_market(market)


def currency_fields_for_candidate(row: dict[str, Any] | None) -> dict[str, str]:
    if not row:
        return {"display_currency": "auto", "display_currency_resolved": "INR"}
    pref = str(row.get("display_currency") or "auto")
    resolved = resolve_display_currency(
        pref,
        market=str(row.get("market") or "IN"),
        location_city=row.get("location_city"),
        location_state=row.get("location_state"),
    )
    return {
        "display_currency": pref if pref in VALID_DISPLAY_CURRENCIES else "auto",
        "display_currency_resolved": resolved,
    }
