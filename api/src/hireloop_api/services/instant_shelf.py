"""Lexical instant job shelf for onboarding — jobs in <30s without embeddings."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg

from hireloop_api.config import Settings

logger = logging.getLogger(__name__)


async def fetch_instant_shelf(
    db: asyncpg.Connection,
    *,
    user_id: str,
    settings: Settings,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return 5–10 market-visible jobs for a fresh candidate using lexical recall.
    Falls back to recent market starter jobs when title search is sparse.
    """
    from hireloop_api.agents.aarya import tools as aarya_tools
    from hireloop_api.routes.matches import _fetch_starter_market_jobs

    candidate = await db.fetchrow(
        """
        SELECT id, looking_for, current_title, market, remote_preference
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )
    if not candidate:
        return []

    query = (
        str(candidate["looking_for"] or "").strip() or str(candidate["current_title"] or "").strip()
    )
    cards: list[dict[str, Any]] = []
    if query:
        try:
            result = await aarya_tools.job_search(
                db,
                user_id,
                "instant-shelf",
                settings=settings,
                query_text=query,
                limit=limit,
            )
            cards = list(result.get("job_cards") or [])
        except Exception as exc:
            logger.warning(
                "instant_shelf_job_search_failed",
                user_id=user_id,
                error=str(exc)[:200],
            )

    if len(cards) >= 5:
        return cards[:limit]

    starter = await _fetch_starter_market_jobs(
        db,
        candidate_id=candidate["id"],
        limit=limit,
        remote_preference=str(candidate.get("remote_preference") or "any"),
        market=str(candidate.get("market") or "IN"),
    )
    seen = {str(c.get("job_id") or c.get("id")) for c in cards}
    for row in starter:
        jid = str(row.get("job_id") or "")
        if jid and jid not in seen:
            cards.append(row)
            seen.add(jid)
        if len(cards) >= limit:
            break
    return cards[:limit]
