"""
Jobs routes — ingestion trigger + public job listing.

POST /api/v1/jobs/ingest          → admin-only: trigger Apify run + upsert
GET  /api/v1/jobs                  → list active jobs (filterable)
GET  /api/v1/jobs/{job_id}         → single job detail
POST /api/v1/jobs/ingest/cron      → called by pg_cron via pg_net (service-secret auth)

Security:
  - /jobs/ingest (POST) — requires admin role (service_role JWT or X-Service-Secret header)
  - /jobs/ingest/cron  — X-Service-Secret header only (no user session)
  - /jobs (GET)        — requires authenticated India-verified user
  - /jobs/{id} (GET)   — requires authenticated India-verified user
"""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_india_verified_user

logger = structlog.get_logger()
router = APIRouter(prefix="/jobs", tags=["jobs"])


# ── Request / Response models ─────────────────────────────────────────────────


class IngestRequest(BaseModel):
    queries: list[str] | None = Field(
        default=None,
        description="Job titles / search queries. Defaults to actor defaults if omitted.",
        examples=[["senior software engineer", "product manager", "data scientist"]],
    )
    locations: list[str] | None = Field(
        default=None,
        description="India cities to scope the search. Defaults to actor defaults.",
        examples=[["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune"]],
    )
    max_results_per_query: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Max results per query x location combo.",
    )


class IngestResponse(BaseModel):
    status: str
    run_id: str | None = None
    dataset_id: str | None = None
    raw_items: int = 0
    normalised: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    elapsed_seconds: float = 0.0
    triggered_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class JobSummary(BaseModel):
    id: str
    title: str
    company_name: str | None
    location_city: str | None
    location_state: str | None
    is_remote: bool
    employment_type: str | None
    seniority: str | None
    ctc_min: int | None  # INR per annum
    ctc_max: int | None  # INR per annum
    skills_required: list[str]
    apply_url: str | None
    source: str | None
    scraped_at: str
    expires_at: str | None


class JobDetail(JobSummary):
    description: str | None
    requirements: str | None
    company_id: str | None
    country_code: str
    apify_job_id: str | None
    is_active: bool
    created_at: str
    updated_at: str


# ── Auth helpers ──────────────────────────────────────────────────────────────


def _verify_service_secret(
    x_service_secret: str | None,
    settings: Settings,
) -> None:
    """Raise 403 if the X-Service-Secret header is missing or wrong (timing-safe)."""
    expected = settings.service_secret or ""
    if not x_service_secret or not expected or not hmac.compare_digest(x_service_secret, expected):
        raise HTTPException(status_code=403, detail="Invalid or missing service secret")


# ── Admin: manual ingest trigger ──────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResponse, status_code=202)
async def trigger_ingest(
    body: IngestRequest,
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> IngestResponse:
    """
    Manually trigger an Apify job scrape + DB upsert (admin only).
    The heavy Apify run is handled via durable background_jobs queue.

    Auth: X-Service-Secret header (matches settings.service_secret).
    """
    _verify_service_secret(x_service_secret, settings)

    from hireloop_api.services.background_jobs import JOB_INGEST, enqueue_job

    await enqueue_job(
        db,
        kind=JOB_INGEST,
        payload={
            "queries": body.queries,
            "locations": body.locations,
            "max_results_per_query": body.max_results_per_query,
        },
    )

    logger.info(
        "job_ingest_queued",
        queries=body.queries,
        locations=body.locations,
        max_per_query=body.max_results_per_query,
    )

    return IngestResponse(status="queued")


# ── pg_cron: nightly ingest trigger (service-secret only) ────────────────────


@router.post("/ingest/cron", response_model=IngestResponse, status_code=202)
async def cron_ingest(
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> IngestResponse:
    """
    Called nightly by pg_cron via pg_net.
    Uses default queries/locations from the Apify actor config.
    Auth: X-Service-Secret header only (no user session).
    """
    _verify_service_secret(x_service_secret, settings)

    from hireloop_api.services.background_jobs import JOB_INGEST, enqueue_job

    await enqueue_job(
        db,
        kind=JOB_INGEST,
        payload={"queries": None, "locations": None, "max_results_per_query": 50},
        idempotency_key="job_ingest:cron",
    )

    logger.info("cron_ingest_queued")
    return IngestResponse(status="queued")


# ── Public: list active jobs ──────────────────────────────────────────────────


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    q: str | None = Query(default=None, description="Free-text filter on title or skills"),
    city: str | None = Query(
        default=None, description="Filter by location_city (case-insensitive)"
    ),
    remote: bool | None = Query(default=None, description="Filter by is_remote"),
    seniority: str | None = Query(default=None, description="Filter by seniority level"),
    employment_type: str | None = Query(default=None, description="Filter by employment type"),
    ctc_min: int | None = Query(default=None, description="Min CTC filter (INR p.a.)"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_india_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """
    List active India jobs with optional filters.
    Always enforces country_code = 'IN' and is_active = TRUE.
    """
    # Build dynamic WHERE clauses
    conditions: list[str] = [
        "j.is_active = TRUE",
        "j.country_code = 'IN'",
        "j.deleted_at IS NULL",
        "j.expires_at > NOW()",
    ]
    params: list[Any] = []
    param_idx = 1

    if q:
        conditions.append(
            f"(j.title ILIKE ${param_idx} OR j.skills_required::text ILIKE ${param_idx})"
        )
        params.append(f"%{q}%")
        param_idx += 1

    if city:
        conditions.append(f"j.location_city ILIKE ${param_idx}")
        params.append(f"%{city}%")
        param_idx += 1

    if remote is not None:
        conditions.append(f"j.is_remote = ${param_idx}")
        params.append(remote)
        param_idx += 1

    if seniority:
        conditions.append(f"j.seniority = ${param_idx}")
        params.append(seniority)
        param_idx += 1

    if employment_type:
        conditions.append(f"j.employment_type = ${param_idx}")
        params.append(employment_type)
        param_idx += 1

    if ctc_min is not None:
        conditions.append(f"(j.ctc_max IS NULL OR j.ctc_max >= ${param_idx})")
        params.append(ctc_min)
        param_idx += 1

    where_clause = " AND ".join(conditions)
    params.extend([limit, offset])

    # S608 is a false positive here: `where_clause` is assembled only from the
    # static condition fragments defined above (no user input is interpolated),
    # and every user-supplied value is passed as a positional asyncpg parameter
    # ($1, $2, …). `param_idx` is an int. The query is fully parameterized.
    query = f"""
        SELECT
            j.id,
            j.title,
            co.name         AS company_name,
            j.location_city,
            j.location_state,
            j.is_remote,
            j.employment_type,
            j.seniority,
            j.ctc_min,
            j.ctc_max,
            j.skills_required,
            j.apply_url,
            j.source,
            j.scraped_at,
            j.expires_at
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE {where_clause}
        ORDER BY j.scraped_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """  # noqa: S608

    rows = await db.fetch(query, *params)

    return [
        {
            **dict(r),
            "id": str(r["id"]),
            "skills_required": r["skills_required"] or [],
            "scraped_at": r["scraped_at"].isoformat() if r["scraped_at"] else None,
            "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
        }
        for r in rows
    ]


# ── Public: single job detail ─────────────────────────────────────────────────


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: str,
    current_user: dict = Depends(get_india_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Fetch full detail for a single job.
    Only returns active IN jobs (country_code enforced).
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format") from None

    row = await db.fetchrow(
        """
        SELECT
            j.id,
            j.title,
            j.description,
            j.requirements,
            co.name         AS company_name,
            j.company_id,
            j.location_city,
            j.location_state,
            j.country_code,
            j.is_remote,
            j.employment_type,
            j.seniority,
            j.ctc_min,
            j.ctc_max,
            j.skills_required,
            j.apply_url,
            j.source,
            j.apify_job_id,
            j.is_active,
            j.scraped_at,
            j.expires_at,
            j.created_at,
            j.updated_at
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.id = $1
          AND j.is_active = TRUE
          AND j.country_code = 'IN'
          AND j.deleted_at IS NULL
        """,
        job_uuid,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        **dict(row),
        "id": str(row["id"]),
        "company_id": str(row["company_id"]) if row["company_id"] else None,
        "skills_required": row["skills_required"] or [],
        "scraped_at": row["scraped_at"].isoformat() if row["scraped_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
