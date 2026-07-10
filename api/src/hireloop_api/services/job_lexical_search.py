"""
Postgres full-text and trigram lexical job retrieval pools.
"""

from __future__ import annotations

from typing import Any

import asyncpg

from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.services.test_jobs import test_jobs_company_sql_exclude


async def fetch_fts_job_pool(
    db: asyncpg.Connection,
    *,
    query: str,
    market: str,
    remote_clause: str,
    fetch_limit: int = 150,
    skills_filter: list[str] | None = None,
    location_city: str | None = None,
) -> list[asyncpg.Record]:
    """Full-text search on jobs.search_tsv (title weighted A, skills B, description C)."""
    if not query or not query.strip():
        return []

    vis = job_visible_for_market_sql(market_param="$4")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")

    try:
        return await db.fetch(
            f"""
            WITH q AS (
                SELECT websearch_to_tsquery('simple', $1) AS tsq
            )
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score,
                   ts_rank_cd(j.search_tsv, q.tsq, 32) AS lexical_score
            FROM public.jobs j
            CROSS JOIN q
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.search_tsv @@ q.tsq
              AND j.is_active = TRUE
              AND {vis}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              {company_exclude}
              AND ($2::text[] IS NULL OR j.skills_required && $2::text[])
              AND ($3::text IS NULL OR j.location_city ILIKE '%' || $3::text || '%')
            ORDER BY lexical_score DESC, j.scraped_at DESC
            LIMIT $5::integer
            """,
            query.strip(),
            skills_filter,
            location_city,
            market,
            fetch_limit,
        )
    except Exception:
        # search_tsv column may not exist yet on older DBs — caller falls back
        return []


async def fetch_trigram_title_pool(
    db: asyncpg.Connection,
    *,
    query: str,
    market: str,
    remote_clause: str,
    fetch_limit: int = 50,
    skills_filter: list[str] | None = None,
    location_city: str | None = None,
) -> list[asyncpg.Record]:
    """Trigram similarity for title spelling variants and aliases."""
    if not query or not query.strip():
        return []

    vis = job_visible_for_market_sql(market_param="$4")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")

    try:
        return await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score,
                   similarity(lower(j.title), lower($1)) AS trigram_score
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.is_active = TRUE
              AND {vis}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              {company_exclude}
              AND similarity(lower(j.title), lower($1)) > 0.25
              AND ($2::text[] IS NULL OR j.skills_required && $2::text[])
              AND ($3::text IS NULL OR j.location_city ILIKE '%' || $3::text || '%')
            ORDER BY trigram_score DESC, j.scraped_at DESC
            LIMIT $5::integer
            """,
            query.strip(),
            skills_filter,
            location_city,
            market,
            fetch_limit,
        )
    except Exception:
        return []


async def fetch_role_family_pool(
    db: asyncpg.Connection,
    *,
    role_id: str,
    market: str,
    remote_clause: str,
    fetch_limit: int = 150,
    location_city: str | None = None,
) -> list[asyncpg.Record]:
    """Jobs tagged with the same occupation role_id."""
    if not role_id or role_id == "general":
        return []

    vis = job_visible_for_market_sql(market_param="$3")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")

    try:
        return await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.role_id = $1
              AND j.is_active = TRUE
              AND {vis}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              {company_exclude}
              AND ($2::text IS NULL OR j.location_city ILIKE '%' || $2::text || '%')
            ORDER BY j.scraped_at DESC
            LIMIT $4::integer
            """,
            role_id,
            location_city,
            market,
            fetch_limit,
        )
    except Exception:
        return []


def records_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
