"""
Shared job pools per canonical career path.

Senior paths (Head of Sales, Head of Growth, etc.) are scraped once into
``career_path_pool_jobs``. Candidates with a matching prioritized title see
pool jobs first; Apify top-up runs only when the pool is thin.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import asyncpg
import structlog

from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.services.titles import title_affinity

logger = structlog.get_logger()

POOL_MATCH_MIN_AFFINITY = 0.28
DEFAULT_POOL_MIN_JOBS = 20

# Seniority/level words appear in almost every title — they must never carry a
# pool match on their own ("Manager - Customer Success" was linking to the
# Engineering Manager pool purely via "manager").
_GENERIC_TITLE_TOKENS = frozenset(
    {
        "manager",
        "management",
        "senior",
        "sr",
        "jr",
        "junior",
        "head",
        "lead",
        "leader",
        "director",
        "vp",
        "president",
        "chief",
        "officer",
        "executive",
        "associate",
        "assistant",
        "principal",
        "staff",
        "specialist",
        "intern",
        "fractional",
    }
)


def _meaningful_tokens(text: str | None) -> frozenset[str]:
    """Title tokens that identify the FUNCTION, not the level."""
    from hireloop_api.services.titles import canonical_title_tokens

    return canonical_title_tokens(text) - _GENERIC_TITLE_TOKENS


def _title_variants(title: str) -> list[str]:
    """The full title plus its slash/dash segments.

    LLM path titles come decorated ("VP Growth / CMO – AI SaaS") and the
    decoration dilutes whole-string token affinity below the match threshold —
    which silently skips the shared pool. Each segment ("VP Growth", "CMO")
    is a clean role phrase worth matching on its own.
    """
    cleaned = (title or "").strip()
    if not cleaned:
        return []
    variants = [cleaned]
    for seg in re.split(r"[/,]|\s[–—-]\s", cleaned):
        s = seg.strip()
        if len(s) >= 3 and s.lower() != cleaned.lower():
            variants.append(s)
    return variants


async def resolve_definition_for_title(
    db: asyncpg.Connection,
    title: str,
    *,
    market: str = "IN",
) -> asyncpg.Record | None:
    """Map a free-text career path title to the best canonical definition."""
    variants = _title_variants(title)
    if not variants:
        return None
    rows = await db.fetch(
        """
        SELECT id, slug, display_title, search_titles, pool_min_jobs, is_senior, market
        FROM public.career_path_definitions
        WHERE market = $1
        """,
        market,
    )
    best: asyncpg.Record | None = None
    best_score = 0.0
    for row in rows:
        candidates = [row["display_title"], *list(row["search_titles"] or [])]
        for candidate in candidates:
            cand_meaningful = _meaningful_tokens(candidate)
            for variant in variants:
                # A pool match must share at least one function token —
                # level words alone ("manager", "head") don't count.
                if not (_meaningful_tokens(variant) & cand_meaningful):
                    continue
                aff = title_affinity(variant, candidate)
                if aff is not None and aff > best_score:
                    best_score = aff
                    best = row
    if best is not None and best_score >= POOL_MATCH_MIN_AFFINITY:
        return best
    return None


async def link_path_to_definition(
    db: asyncpg.Connection,
    career_path_id: uuid.UUID,
    prioritized_title: str,
    *,
    market: str = "IN",
) -> uuid.UUID | None:
    """Persist the canonical definition on a candidate's career_paths row."""
    definition = await resolve_definition_for_title(db, prioritized_title, market=market)
    if definition is None:
        return None
    await db.execute(
        """
        UPDATE public.career_paths
        SET career_path_definition_id = $2, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        career_path_id,
        definition["id"],
    )
    return definition["id"]


async def pool_job_count(db: asyncpg.Connection, definition_id: uuid.UUID) -> int:
    val = await db.fetchval(
        """
        SELECT COUNT(*)::int
        FROM public.career_path_pool_jobs cpj
        JOIN public.jobs j ON j.id = cpj.job_id
        WHERE cpj.career_path_definition_id = $1::uuid
          AND j.is_active = TRUE
          AND j.deleted_at IS NULL
          AND j.expires_at > NOW()
        """,
        definition_id,
    )
    return int(val or 0)


async def fetch_scored_pool_jobs(
    db: asyncpg.Connection,
    candidate_id: str,
    definition_id: uuid.UUID,
    limit: int,
    *,
    remote_preference: str = "any",
    market: str = "IN",
) -> list[asyncpg.Record]:
    """Jobs from the shared pool, ranked by this candidate's match_scores."""
    from hireloop_api.services.job_preferences import remote_filter_sql

    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$4")
    return await db.fetch(
        f"""
        SELECT j.id AS job_id, j.title, co.name AS company_name,
               j.location_city, j.location_state, j.is_remote,
               j.employment_type, j.seniority, j.ctc_min, j.ctc_max,
               j.skills_required, j.apply_url,
               ms.overall_score, ms.skills_score, ms.experience_score,
               ms.location_score, ms.ctc_score, ms.explanation, ms.computed_at
        FROM public.career_path_pool_jobs cpj
        JOIN public.jobs j ON j.id = cpj.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.match_scores ms
          ON ms.job_id = j.id AND ms.candidate_id = $1::uuid
        WHERE cpj.career_path_definition_id = $2::uuid
          AND j.is_active = TRUE
          AND j.deleted_at IS NULL
          AND j.expires_at > NOW()
          AND {vis}
          {remote_clause}
        ORDER BY ms.overall_score DESC NULLS LAST, cpj.added_at DESC
        LIMIT $3
        """,
        uuid.UUID(candidate_id),
        definition_id,
        limit,
        market,
    )


async def refresh_pool_membership(
    db: asyncpg.Connection,
    definition_id: uuid.UUID,
    search_titles: list[str],
    *,
    source: str = "pool_ingest",
) -> int:
    """Link active jobs whose titles match the definition's search queries."""
    linked = 0
    for raw in search_titles:
        title = (raw or "").strip()
        if len(title) < 3:
            continue
        result = await db.execute(
            """
            INSERT INTO public.career_path_pool_jobs
              (career_path_definition_id, job_id, source)
            SELECT $1::uuid, j.id, $3
            FROM public.jobs j
            WHERE j.deleted_at IS NULL
              AND j.is_active = TRUE
              AND j.expires_at > NOW()
              AND j.title ILIKE $2
            ON CONFLICT DO NOTHING
            """,
            definition_id,
            f"%{title}%",
            source,
        )
        if result and result.startswith("INSERT"):
            try:
                linked += int(result.split()[-1])
            except (ValueError, IndexError):
                pass
    await db.execute(
        """
        UPDATE public.career_path_definitions
        SET last_ingested_at = NOW()
        WHERE id = $1::uuid
        """,
        definition_id,
    )
    return linked


async def score_pool_for_candidate(
    db: asyncpg.Connection,
    candidate_id: str,
    definition_id: uuid.UUID,
) -> int:
    """Score all pool jobs for one candidate (best-effort)."""
    from hireloop_api.services.matching import MatchingEngine

    job_ids = await db.fetch(
        """
        SELECT job_id FROM public.career_path_pool_jobs
        WHERE career_path_definition_id = $1::uuid
        """,
        definition_id,
    )
    if not job_ids:
        return 0
    engine = MatchingEngine(db)
    scored = 0
    for row in job_ids:
        result = await engine.score_pair(candidate_id, str(row["job_id"]), notify=False)
        if result is not None:
            scored += 1
    return scored


async def ingest_pool(
    settings: Any,
    *,
    definition_id: str,
    candidate_id: str | None = None,
    locations: list[str] | None = None,
) -> dict[str, Any]:
    """Scrape jobs for a canonical path and refresh pool membership."""
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.apify.job_ingester import JobIngester

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, slug, search_titles, market, is_senior
            FROM public.career_path_definitions
            WHERE id = $1::uuid
            """,
            uuid.UUID(definition_id),
        )
        if not row:
            return {"error": "definition_not_found"}

        queries = list(row["search_titles"] or [])
        locs = locations or ["India"]
        stats: dict[str, Any] = {"definition_id": definition_id, "slug": row["slug"]}

        if settings.apify_token:
            ingester = JobIngester(
                apify_token=settings.apify_token,
                db=conn,
                settings=settings,
                linkedin_actor=settings.apify_linkedin_jobs_actor,
                career_site_actor=settings.apify_career_site_actor,
                enable_career_site=settings.apify_enable_career_site_ingest,
            )
            ingest_stats = await ingester.ingest(
                queries=queries,
                locations=locs,
                max_results_per_query=40 if row["is_senior"] else 25,
                # 7d was too narrow for exact-title pools (Customer Success in
                # India returned zero); the per-query limit caps cost anyway.
                time_range="6m" if row["is_senior"] else "30d",
            )
            stats["ingest"] = ingest_stats
        else:
            stats["ingest"] = {"skipped": "no_apify_token"}

        linked = await refresh_pool_membership(conn, row["id"], queries)
        stats["pool_linked"] = linked
        stats["pool_total"] = await pool_job_count(conn, row["id"])

        if candidate_id:
            try:
                stats["scored"] = await score_pool_for_candidate(conn, candidate_id, row["id"])
            except Exception as exc:
                logger.warning("pool_score_failed", error=str(exc)[:200])
                stats["scored"] = 0

        logger.info("career_path_pool_ingest_done", **stats)
        return stats
