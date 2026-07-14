"""Lexical instant job shelf for onboarding — jobs in <30s without embeddings."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg

from hireloop_api.config import Settings

logger = logging.getLogger(__name__)

_INSTANT_SHELF_SESSION_NAMESPACE = uuid.UUID("b725c93d-d17f-4fc0-b1b8-c81538d01a27")


async def _persist_instant_shelf(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    cards: list[dict[str, Any]],
) -> None:
    """Persist every onboarding card so Job History survives browser refresh."""
    from hireloop_api.agents.aarya.tools import _persist_chat_match_scores

    await _persist_chat_match_scores(db, candidate_id=candidate_id, rows=cards)
    job_ids: list[uuid.UUID] = []
    for card in cards:
        raw_id = card.get("job_id") or card.get("id")
        try:
            job_ids.append(uuid.UUID(str(raw_id)))
        except (TypeError, ValueError):
            continue
    if not job_ids:
        return
    await db.execute(
        """
        INSERT INTO public.candidate_job_impressions (candidate_id, job_id, source)
        SELECT $1::uuid, jid, 'matches'
        FROM unnest($2::uuid[]) AS jid
        ON CONFLICT (candidate_id, job_id) DO UPDATE
        SET last_seen_at = NOW(),
            seen_count = public.candidate_job_impressions.seen_count + 1,
            source = EXCLUDED.source,
            updated_at = NOW()
        """,
        candidate_id,
        job_ids,
    )


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
            session_id = str(uuid.uuid5(_INSTANT_SHELF_SESSION_NAMESPACE, str(candidate["id"])))
            result = await aarya_tools.job_search(
                db,
                user_id,
                session_id,
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

    if len(cards) < 5:
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

    final_cards = cards[:limit]
    await _persist_instant_shelf(
        db,
        candidate_id=uuid.UUID(str(candidate["id"])),
        cards=final_cards,
    )
    return final_cards
