"""Public market catalog — supported home markets for job visibility."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from hireloop_api.config import Settings, get_settings
from hireloop_api.markets import (
    MARKET_CURRENCIES,
    MARKET_LABELS,
    SUPPORTED_MARKETS,
    dial_prefix_for_market,
    market_catalog,
)

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("")
async def list_markets(
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Supported home markets and which are enabled for job ingest in this deployment.
    """
    enabled = {m.upper() for m in settings.enabled_markets}
    markets = []
    for entry in market_catalog():
        code = entry["code"]
        markets.append(
            {
                **entry,
                "ingest_enabled": code in enabled,
            }
        )
    return {
        "markets": markets,
        "default_market": settings.default_market,
        "supported_codes": sorted(SUPPORTED_MARKETS),
        "enabled_codes": sorted(enabled & SUPPORTED_MARKETS),
        "labels": MARKET_LABELS,
        "currencies": MARKET_CURRENCIES,
        "dial_prefixes": {code: dial_prefix_for_market(code) for code in sorted(SUPPORTED_MARKETS)},
    }
