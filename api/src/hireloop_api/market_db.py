"""DB helpers for candidate market resolution."""

from __future__ import annotations

import uuid

import asyncpg

from hireloop_api.markets import normalize_market


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


async def fetch_user_market(db: asyncpg.Connection, user_id: uuid.UUID) -> str:
    row = await db.fetchrow(
        "SELECT market FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        user_id,
    )
    if not row:
        return normalize_market(None)
    market = row["market"] if "market" in row else row.get("market")  # type: ignore[attr-defined]
    return normalize_market(market if isinstance(market, str) else None)
