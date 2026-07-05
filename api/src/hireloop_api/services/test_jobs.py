"""
Test jobs from rupesh.kumar@candidate.ly — shown to every candidate for MVP testing.

These roles bypass career-path / persona / domain-fit gates so anyone can discover
them, chat with Aarya, and try the intro connection flow.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg

from hireloop_api.markets import job_visible_for_market_sql, normalize_market
from hireloop_api.services.job_preferences import remote_filter_sql

TEST_RECRUITER_EMAIL = "rupesh.kumar@candidate.ly"
TEST_COMPANY_DOMAIN = "hireloop-test.in"
TEST_COMPANY_NAME = "Hireloop Test Co"
TEST_MATCH_SCORE = 0.75
TEST_MATCH_EXPLANATION = (
    "Hireloop test role — use this to try job discovery, chat, and intro requests."
)


def is_test_job(job_row: Mapping[str, Any]) -> bool:
    """True when the job was seeded for internal connection/chat testing."""
    domain = (job_row.get("company_domain") or "").lower()
    if domain == TEST_COMPANY_DOMAIN:
        return True
    name = (job_row.get("company_name") or "").strip()
    if name == TEST_COMPANY_NAME:
        return True
    email = (job_row.get("recruiter_email") or "").lower()
    return email == TEST_RECRUITER_EMAIL


def _test_job_sql_predicate(*, company_alias: str = "co", user_alias: str = "u") -> str:
    return f"""(
        {company_alias}.domain = '{TEST_COMPANY_DOMAIN}'
        OR {company_alias}.name = '{TEST_COMPANY_NAME}'
        OR {user_alias}.email = '{TEST_RECRUITER_EMAIL}'
    )"""


async def fetch_test_jobs(
    db: asyncpg.Connection,
    *,
    market: str = "IN",
    remote_preference: str = "any",
) -> list[asyncpg.Record]:
    """Active test jobs for the candidate's market (ignores career-path fit)."""
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$1")
    predicate = _test_job_sql_predicate()
    return await db.fetch(
        f"""
        SELECT j.id AS job_id, j.title, co.name AS company_name, co.domain AS company_domain,
               j.location_city, j.location_state, j.is_remote,
               j.employment_type, j.seniority, j.ctc_min, j.ctc_max,
               j.salary_currency, j.skills_required, j.description, j.apply_url,
               u.email AS recruiter_email
        FROM public.jobs j
        JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.recruiters r ON r.id = j.recruiter_id AND r.deleted_at IS NULL
        LEFT JOIN public.users u ON u.id = r.user_id AND u.deleted_at IS NULL
        WHERE j.is_active = TRUE
          AND j.deleted_at IS NULL
          AND (j.expires_at IS NULL OR j.expires_at > NOW())
          AND {vis}
          AND {predicate}
          {remote_clause}
        ORDER BY j.scraped_at DESC NULLS LAST
        """,
        normalize_market(market),
    )


async def ensure_test_match_scores(
    db: asyncpg.Connection,
    candidate_id: str,
    *,
    market: str = "IN",
    remote_preference: str = "any",
) -> None:
    """Upsert match_scores so test jobs appear in feed/search for every candidate."""
    rows = await fetch_test_jobs(db, market=market, remote_preference=remote_preference)
    if not rows:
        return

    bias_audit = json.dumps({"test_job": True, "bypass": "goal_filters"})
    records = [
        (
            uuid.uuid4(),
            uuid.UUID(candidate_id),
            row["job_id"],
            TEST_MATCH_SCORE,
            TEST_MATCH_SCORE,
            TEST_MATCH_SCORE,
            TEST_MATCH_SCORE,
            TEST_MATCH_SCORE,
            TEST_MATCH_EXPLANATION,
            bias_audit,
        )
        for row in rows
    ]
    await db.executemany(
        """
        INSERT INTO public.match_scores
            (id, candidate_id, job_id,
             overall_score, skills_score, experience_score, location_score, ctc_score,
             explanation, bias_audit, computed_at)
        VALUES
            ($1, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10::jsonb, NOW())
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
            overall_score = GREATEST(match_scores.overall_score, EXCLUDED.overall_score),
            explanation = EXCLUDED.explanation,
            computed_at = NOW()
        """,
        records,
    )


def serialize_test_job_for_feed(row: Mapping[str, Any]) -> dict[str, Any]:
    """Shape a test job row like GET /matches feed items."""
    job_skills = list(row.get("skills_required") or [])
    return {
        "job_id": str(row["job_id"]),
        "title": row["title"],
        "company_name": row.get("company_name"),
        "location_city": row.get("location_city"),
        "location_state": row.get("location_state"),
        "is_remote": bool(row.get("is_remote")),
        "employment_type": row.get("employment_type"),
        "seniority": row.get("seniority"),
        "ctc_min": row.get("ctc_min"),
        "ctc_max": row.get("ctc_max"),
        "salary_currency": row.get("salary_currency"),
        "skills_required": job_skills,
        "description": row.get("description"),
        "apply_url": row.get("apply_url"),
        "overall_score": TEST_MATCH_SCORE,
        "skills_score": TEST_MATCH_SCORE,
        "experience_score": TEST_MATCH_SCORE,
        "location_score": TEST_MATCH_SCORE,
        "ctc_score": TEST_MATCH_SCORE,
        "explanation": TEST_MATCH_EXPLANATION,
        "computed_at": datetime.now(UTC).isoformat(),
        "action_state": None,
        "action_label": None,
    }


async def fetch_test_jobs_for_feed(
    db: asyncpg.Connection,
    *,
    market: str = "IN",
    remote_preference: str = "any",
) -> list[dict[str, Any]]:
    rows = await fetch_test_jobs(db, market=market, remote_preference=remote_preference)
    return [serialize_test_job_for_feed(dict(r)) for r in rows]


def prepend_test_jobs(
    jobs: list[dict[str, Any]],
    test_jobs: list[dict[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Put test jobs first; dedupe by job_id."""
    seen = {str(j.get("job_id") or j.get("id")) for j in test_jobs}
    merged = list(test_jobs)
    for job in jobs:
        jid = str(job.get("job_id") or job.get("id"))
        if jid in seen:
            continue
        seen.add(jid)
        merged.append(job)
    if limit is not None:
        return merged[:limit]
    return merged
