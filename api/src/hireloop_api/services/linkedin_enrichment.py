"""LinkedIn profile enrichment scheduling (via LinkDAPI — linkdapi.com)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.deps import get_db_pool
from hireloop_api.services.linkdapi_profile import enrich_candidate_via_linkdapi
from hireloop_api.services.linkedin_oauth import (
    candidate_needs_linkedin_extraction,
)

logger = structlog.get_logger()


def _enrichment_enabled(settings: Settings) -> bool:
    return bool(settings.linkdapi_key)


async def _enrich(
    conn: asyncpg.Connection, settings: Settings, *, user_id: str, profile_url: str
) -> dict[str, Any]:
    return await enrich_candidate_via_linkdapi(
        conn,
        user_id=user_id,
        profile_url=profile_url,
        api_key=settings.linkdapi_key,
        base_url=settings.linkdapi_base_url,
    )


async def enrich_linkedin_profile_background(
    *,
    user_id: str,
    linkedin_url: str,
    settings: Settings,
) -> None:
    """Fire-and-forget LinkDAPI enrichment for one candidate (own DB connection)."""
    if not _enrichment_enabled(settings):
        logger.info(
            "linkedin_profile_enrichment_disabled",
            user_id=user_id,
            reason="linkdapi_key_missing",
        )
        return

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        try:
            result = await _enrich(conn, settings, user_id=user_id, profile_url=linkedin_url)
            logger.info("linkedin_profile_enrichment_done", user_id=user_id, **result)
        except Exception as exc:
            logger.warning(
                "linkedin_profile_enrichment_failed",
                user_id=user_id,
                error=str(exc)[:300],
            )


def _coerce_linkedin_data(raw: Any) -> dict[str, Any]:  # noqa: ANN401
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def list_pending_linkedin_enrichments(
    db: asyncpg.Connection,
    *,
    limit: int = 100,
) -> list[dict[str, str]]:
    """Candidates with a resolvable LinkedIn URL still needing enrichment."""
    rows = await db.fetch(
        """
        SELECT c.user_id, c.linkedin_url, c.linkedin_data
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.deleted_at IS NULL
          AND u.role = 'candidate'
        ORDER BY c.updated_at ASC
        LIMIT $1::integer
        """,
        max(1, min(limit * 5, 500)),
    )

    pending: list[dict[str, str]] = []
    for row in rows:
        if len(pending) >= limit:
            break
        blob = _coerce_linkedin_data(row["linkedin_data"])
        needs, profile_url = candidate_needs_linkedin_extraction(
            linkedin_url=row.get("linkedin_url"),
            linkedin_data=blob,
            force_retry=True,
        )
        if not needs or not profile_url:
            continue
        pending.append(
            {
                "user_id": str(row["user_id"]),
                "profile_url": profile_url,
            }
        )
    return pending


async def backfill_linkedin_profiles(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    limit: int = 50,
    delay_seconds: float = 2.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run LinkDAPI enrichment for candidates still missing profile data."""
    if not _enrichment_enabled(settings):
        return {
            "status": "skipped",
            "reason": "linkdapi_key_missing",
            "pending": 0,
            "processed": 0,
        }

    pending = await list_pending_linkedin_enrichments(db, limit=limit)
    if dry_run:
        return {
            "status": "dry_run",
            "pending": len(pending),
            "user_ids": [p["user_id"] for p in pending],
        }

    results: list[dict[str, Any]] = []
    for item in pending:
        try:
            outcome = await _enrich(
                db, settings, user_id=item["user_id"], profile_url=item["profile_url"]
            )
            results.append({"user_id": item["user_id"], **outcome})
        except Exception as exc:
            results.append(
                {
                    "user_id": item["user_id"],
                    "status": "error",
                    "error": str(exc)[:200],
                }
            )
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    enriched = sum(1 for r in results if r.get("status") == "enriched")
    empty = sum(1 for r in results if r.get("status") in ("empty", "skipped"))
    errors = sum(1 for r in results if r.get("status") == "error")

    return {
        "status": "done",
        "pending": len(pending),
        "processed": len(results),
        "enriched": enriched,
        "empty": empty,
        "errors": errors,
        "results": results,
    }


def should_schedule_linkedin_enrichment(
    *,
    linkedin_url: str | None,
    linkedin_data: Any,  # noqa: ANN401
    settings: Settings | None = None,
    retry_after_hours: float = 6.0,
) -> tuple[bool, str | None]:
    """Schedule background enrichment when extraction is missing (respects cooldown)."""
    from hireloop_api.config import get_settings

    cfg = settings or get_settings()
    if not _enrichment_enabled(cfg):
        return False, None
    return candidate_needs_linkedin_extraction(
        linkedin_url=linkedin_url,
        linkedin_data=_coerce_linkedin_data(linkedin_data),
        force_retry=False,
        retry_after_hours=retry_after_hours,
    )


async def run_startup_linkedin_extraction_batch(
    settings: Settings,
    *,
    limit: int = 15,
) -> None:
    """On API boot, enrich candidates still missing LinkedIn profile data."""
    if not _enrichment_enabled(settings) or not settings.database_url:
        return

    await asyncio.sleep(3)

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        try:
            summary = await backfill_linkedin_profiles(
                conn,
                settings,
                limit=limit,
                delay_seconds=2.0,
            )
            logger.info("startup_linkedin_extraction_batch", **summary)
        except Exception as exc:
            logger.warning(
                "startup_linkedin_extraction_batch_failed",
                error=str(exc)[:300],
            )
