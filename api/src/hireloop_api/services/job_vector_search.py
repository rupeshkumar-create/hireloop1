"""
Live pgvector retrieval pools for job search.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.services.job_visibility import LIVE_JOB_VISIBLE_SQL
from hireloop_api.services.test_jobs import test_jobs_company_sql_exclude


async def _candidate_embedding(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    column: str,
) -> list[float] | None:
    row = await db.fetchrow(
        f"""
        SELECT {column}::text AS emb
        FROM public.candidate_embeddings
        WHERE candidate_id = $1
        """,
        candidate_id,
    )
    if not row:
        return None
    emb = row.get("emb") if hasattr(row, "get") else row["emb"]
    if not emb:
        return None
    if isinstance(emb, str):
        inner = emb.strip("[]")
        if not inner:
            return None
        return [float(x) for x in inner.split(",")]
    return list(emb) if emb else None


async def fetch_title_vector_pool(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    market: str,
    remote_clause: str,
    fetch_limit: int = 150,
    location_city: str | None = None,
) -> list[asyncpg.Record]:
    """Cosine similarity on job title_embedding vs candidate profile_embedding."""
    emb = await _candidate_embedding(db, candidate_id, "profile_embedding")
    if not emb:
        return []

    vis = job_visible_for_market_sql(market_param="$4")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")
    vec_literal = "[" + ",".join(str(x) for x in emb) + "]"

    try:
        return await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score,
                   1 - (je.title_embedding <=> $1::vector) AS vector_score
            FROM public.job_embeddings je
            JOIN public.jobs j ON j.id = je.job_id
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE je.title_embedding IS NOT NULL
              AND j.is_active = TRUE
              AND {vis}
              AND j.deleted_at IS NULL
              AND {LIVE_JOB_VISIBLE_SQL}
              {remote_clause}
              {company_exclude}
              AND ($2::text IS NULL OR j.location_city ILIKE '%' || $2::text || '%')
            ORDER BY je.title_embedding <=> $1::vector
            LIMIT $3::integer
            """,
            vec_literal,
            location_city,
            fetch_limit,
            market,
        )
    except Exception:
        return []


async def fetch_responsibility_vector_pool(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    market: str,
    remote_clause: str,
    fetch_limit: int = 150,
    location_city: str | None = None,
) -> list[asyncpg.Record]:
    """Cosine similarity on job jd_embedding vs candidate resume_embedding."""
    emb = await _candidate_embedding(db, candidate_id, "resume_embedding")
    if not emb:
        emb = await _candidate_embedding(db, candidate_id, "profile_embedding")
    if not emb:
        return []

    vis = job_visible_for_market_sql(market_param="$4")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")
    vec_literal = "[" + ",".join(str(x) for x in emb) + "]"

    try:
        return await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score,
                   1 - (je.jd_embedding <=> $1::vector) AS vector_score
            FROM public.job_embeddings je
            JOIN public.jobs j ON j.id = je.job_id
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE je.jd_embedding IS NOT NULL
              AND j.is_active = TRUE
              AND {vis}
              AND j.deleted_at IS NULL
              AND {LIVE_JOB_VISIBLE_SQL}
              {remote_clause}
              {company_exclude}
              AND ($2::text IS NULL OR j.location_city ILIKE '%' || $2::text || '%')
            ORDER BY je.jd_embedding <=> $1::vector
            LIMIT $3::integer
            """,
            vec_literal,
            location_city,
            fetch_limit,
            market,
        )
    except Exception:
        return []


def records_to_dicts(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
