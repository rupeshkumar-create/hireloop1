"""
Shared job-search inventory buckets — scrape once, serve many candidates.

Bucket key: role_id|market|location|language
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from hireloop_api.services.occupation_taxonomy import resolve_role_id

logger = structlog.get_logger()

# Minimum active jobs before bucket is considered healthy
MIN_BUCKET_INVENTORY = 8
# Hours before a bucket is stale and eligible for refresh
BUCKET_FRESHNESS_HOURS = 12
# Query plan version — bump to force refresh all buckets
QUERY_PLAN_VERSION = 2


def bucket_key(
    *,
    role_id: str,
    market: str,
    location: str | None,
    language: str = "en",
) -> str:
    loc = (location or "any").strip().lower()
    return f"{role_id}|{market.upper()}|{loc}|{language.lower()}"


def bucket_idempotency_key(bucket: str) -> str:
    return f"job_bucket:{bucket}:v{QUERY_PLAN_VERSION}"


async def bucket_stats(
    db: asyncpg.Connection,
    *,
    bucket: str,
) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT bucket_key, role_id, market, location_norm, language,
               active_job_count, last_success_at, query_plan_version, last_run_at
        FROM public.job_search_buckets
        WHERE bucket_key = $1
        """,
        bucket,
    )
    return dict(row) if row else None


async def bucket_needs_refresh(
    db: asyncpg.Connection,
    *,
    bucket: str,
    minimum_inventory: int = MIN_BUCKET_INVENTORY,
) -> bool:
    stats = await bucket_stats(db, bucket=bucket)
    if not stats:
        return True
    if stats.get("query_plan_version", 0) != QUERY_PLAN_VERSION:
        return True
    if (stats.get("active_job_count") or 0) < minimum_inventory:
        return True
    last = stats.get("last_success_at")
    if not last:
        return True
    cutoff = datetime.now(UTC) - timedelta(hours=BUCKET_FRESHNESS_HOURS)
    if last < cutoff:
        return True
    return False


async def resolve_bucket_for_candidate(
    db: asyncpg.Connection,
    *,
    candidate_id: str,
    market: str,
    location: str | None = None,
) -> tuple[str, str, list[str]]:
    """Return (bucket_key, role_id, apify_queries) for a candidate."""
    from hireloop_api.services.occupation_taxonomy import apify_query_variants

    row = await db.fetchrow(
        """
        SELECT c.current_title, c.looking_for, cp.prioritized_title, cp.target_titles
        FROM public.candidates c
        LEFT JOIN LATERAL (
            SELECT prioritized_title, target_titles
            FROM public.career_paths
            WHERE candidate_id = c.id AND deleted_at IS NULL
            ORDER BY created_at DESC LIMIT 1
        ) cp ON TRUE
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    primary = None
    alternates: list[str] = []
    if row:
        primary = (
            row.get("prioritized_title")
            or row.get("looking_for")
            or row.get("current_title")
        )
        alternates = list(row.get("target_titles") or [])

    role_id = resolve_role_id(str(primary) if primary else None) or "general"
    queries = apify_query_variants(
        primary_title=str(primary or "Software Engineer"),
        role_id=role_id if role_id != "general" else None,
        alternate_titles=alternates[:3],
        max_queries=4,
    )
    key = bucket_key(role_id=role_id, market=market, location=location)
    return key, role_id, queries


async def record_bucket_success(
    db: asyncpg.Connection,
    *,
    bucket: str,
    role_id: str,
    market: str,
    location: str | None,
    active_count: int,
) -> None:
    loc_norm = (location or "any").strip().lower()
    await db.execute(
        """
        INSERT INTO public.job_search_buckets
          (bucket_key, role_id, market, location_norm, language,
           active_job_count, last_success_at, last_run_at, query_plan_version)
        VALUES ($1, $2, $3, $4, 'en', $5, NOW(), NOW(), $6)
        ON CONFLICT (bucket_key) DO UPDATE SET
          active_job_count = EXCLUDED.active_job_count,
          last_success_at = NOW(),
          last_run_at = NOW(),
          query_plan_version = EXCLUDED.query_plan_version,
          updated_at = NOW()
        """,
        bucket,
        role_id,
        market.upper(),
        loc_norm,
        active_count,
        QUERY_PLAN_VERSION,
    )


def canonical_job_fingerprint(
    *,
    company_name: str | None,
    title: str | None,
    location: str | None,
    description_prefix: str | None = None,
) -> str:
    """Conservative cross-source dedup fingerprint."""
    parts = [
        (company_name or "").strip().lower(),
        (title or "").strip().lower(),
        (location or "").strip().lower(),
        (description_prefix or "")[:200].strip().lower(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
