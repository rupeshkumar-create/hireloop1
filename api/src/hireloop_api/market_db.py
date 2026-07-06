"""DB helpers for candidate market resolution."""

from __future__ import annotations

import uuid

import asyncpg

from hireloop_api.markets import SUPPORTED_MARKETS, normalize_market, resolve_country_from_location


async def fetch_candidate_market(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> str:
    row = await db.fetchrow(
        """
        SELECT COALESCE(NULLIF(c.market, ''), NULLIF(u.market, ''), 'IN') AS market
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    if not row:
        return normalize_market(None)
    # Test doubles sometimes return dicts without the expected column keys.
    market = row["market"] if "market" in row else row.get("market")  # type: ignore[attr-defined]
    return normalize_market(market if isinstance(market, str) else None)


async def sync_candidate_market_from_location(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    location_city: str | None = None,
    location_state: str | None = None,
) -> str | None:
    """
    When profile location implies a supported market, persist it on user + candidate.
    Returns the market code when updated, else None.
    """
    loc = ", ".join(p for p in (location_city, location_state) if p and str(p).strip())
    inferred = resolve_country_from_location(loc)
    if not inferred:
        return None
    market = normalize_market(inferred)
    await db.execute(
        """
        UPDATE public.candidates c
        SET market = $2, updated_at = NOW()
        WHERE c.id = $1::uuid
          AND c.deleted_at IS NULL
          AND (c.market IS NULL OR c.market = 'IN' OR c.market <> $2)
        """,
        candidate_id,
        market,
    )
    await db.execute(
        """
        UPDATE public.users u
        SET market = $2, phone_country = $2, updated_at = NOW()
        FROM public.candidates c
        WHERE c.id = $1::uuid
          AND c.user_id = u.id
          AND u.deleted_at IS NULL
          AND (u.market IS NULL OR u.market = 'IN' OR u.market <> $2)
        """,
        candidate_id,
        market,
    )
    return market


def infer_market_from_geo_country(country_code: str | None) -> str | None:
    """Map ISO country code from CDN/WAF geo headers to a supported market."""
    if not country_code:
        return None
    code = country_code.upper().strip()
    if code == "UK":
        code = "GB"
    if code in SUPPORTED_MARKETS:
        return code
    return None


async def fetch_user_market(db: asyncpg.Connection, user_id: uuid.UUID) -> str:
    row = await db.fetchrow(
        "SELECT market FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        user_id,
    )
    if not row:
        return normalize_market(None)
    market = row["market"] if "market" in row else row.get("market")  # type: ignore[attr-defined]
    return normalize_market(market if isinstance(market, str) else None)
