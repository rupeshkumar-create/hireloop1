"""
Hiring manager routes — HM lookup, creation, and enrichment trigger.

POST /api/v1/hiring-managers                      → create HM record (admin/Nitya)
GET  /api/v1/hiring-managers/{hm_id}              → get HM detail
GET  /api/v1/hiring-managers/by-company/{co_id}   → list HMs at a company
POST /api/v1/hiring-managers/{hm_id}/enrich       → trigger enrichment waterfall
GET  /api/v1/hiring-managers/{hm_id}/enrich/status → poll enrichment status

Auth: X-Service-Secret on all write/enrich endpoints (called by Nitya agent or admin).
GET endpoints require India-verified user.
"""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_india_verified_user

logger = structlog.get_logger()
router = APIRouter(prefix="/hiring-managers", tags=["hiring-managers"])


# ── Auth ──────────────────────────────────────────────────────────────────────


def _require_secret(x_service_secret: str | None, settings: Settings) -> None:
    if not x_service_secret or x_service_secret != settings.service_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing service secret")


# ── Models ────────────────────────────────────────────────────────────────────


class CreateHMRequest(BaseModel):
    company_id: str
    full_name: str
    title: str | None = None
    linkedin_url: str | None = None
    email: str | None = None


class HMDetail(BaseModel):
    id: str
    company_id: str | None
    full_name: str
    title: str | None
    email: str | None
    email_verified: bool
    linkedin_url: str | None
    enrich_status: str
    last_enriched: str | None
    created_at: str


class EnrichStatusResponse(BaseModel):
    hm_id: str
    enrich_status: str
    email: str | None
    email_verified: bool
    last_enriched: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=HMDetail, status_code=201)
async def create_hiring_manager(
    body: CreateHMRequest,
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Create a new hiring_manager record.
    Called by the Nitya agent when processing an intro_request.
    Auth: X-Service-Secret.
    """
    _require_secret(x_service_secret, settings)

    # Deduplicate on LinkedIn URL
    if body.linkedin_url:
        existing = await db.fetchrow(
            "SELECT id FROM public.hiring_managers WHERE linkedin_url = $1 AND deleted_at IS NULL",
            body.linkedin_url,
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"HM with this LinkedIn URL already exists: {existing['id']}",
            )

    hm_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO public.hiring_managers
            (id, company_id, full_name, title, linkedin_url, email)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
        """,
        hm_id,
        uuid.UUID(body.company_id),
        body.full_name,
        body.title,
        body.linkedin_url,
        body.email,
    )

    row = await db.fetchrow("SELECT * FROM public.hiring_managers WHERE id = $1::uuid", hm_id)
    return _hm_to_dict(row)


@router.get("/{hm_id}", response_model=HMDetail)
async def get_hiring_manager(
    hm_id: str,
    _current_user: dict = Depends(get_india_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Fetch a single hiring manager by ID."""
    try:
        hm_uuid = uuid.UUID(hm_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid HM ID") from exc

    row = await db.fetchrow(
        "SELECT * FROM public.hiring_managers WHERE id = $1::uuid AND deleted_at IS NULL",
        hm_uuid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Hiring manager not found")

    return _hm_to_dict(row)


@router.get("/by-company/{company_id}", response_model=list[HMDetail])
async def list_hms_by_company(
    company_id: str,
    _current_user: dict = Depends(get_india_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """List hiring managers associated with a company."""
    try:
        co_uuid = uuid.UUID(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid company ID") from exc

    rows = await db.fetch(
        """
        SELECT * FROM public.hiring_managers
        WHERE company_id = $1::uuid AND deleted_at IS NULL
        ORDER BY email_verified DESC, last_enriched DESC NULLS LAST
        LIMIT 20
        """,
        co_uuid,
    )
    return [_hm_to_dict(r) for r in rows]


@router.post("/{hm_id}/enrich", status_code=202)
async def trigger_enrich(
    hm_id: str,
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Trigger the Apify enrichment waterfall for a hiring manager.
    Runs in background — poll /enrich/status for progress.
    Auth: X-Service-Secret.
    """
    _require_secret(x_service_secret, settings)

    try:
        hm_uuid = uuid.UUID(hm_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid HM ID") from exc

    row = await db.fetchrow(
        "SELECT id, enrich_status FROM public.hiring_managers "
        "WHERE id = $1::uuid AND deleted_at IS NULL",
        hm_uuid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Hiring manager not found")

    if row["enrich_status"] == "in_progress":
        return {"status": "already_running", "hm_id": hm_id}

    from hireloop_api.services.background_jobs import HM_ENRICH, enqueue_job

    await enqueue_job(
        db,
        kind=HM_ENRICH,
        payload={"hm_id": hm_id},
        idempotency_key=f"hm_enrich:{hm_id}",
    )
    return {"status": "queued", "hm_id": hm_id}


@router.get("/{hm_id}/enrich/status", response_model=EnrichStatusResponse)
async def get_enrich_status(
    hm_id: str,
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Poll enrichment status. Auth: X-Service-Secret."""
    _require_secret(x_service_secret, settings)

    try:
        hm_uuid = uuid.UUID(hm_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid HM ID") from exc

    row = await db.fetchrow(
        """
        SELECT id, enrich_status, email, email_verified, last_enriched
        FROM public.hiring_managers
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        hm_uuid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Hiring manager not found")

    return {
        "hm_id": str(row["id"]),
        "enrich_status": row["enrich_status"],
        "email": row["email"] if row["email_verified"] else None,
        "email_verified": row["email_verified"],
        "last_enriched": row["last_enriched"].isoformat() if row["last_enriched"] else None,
    }


# ── Serialiser ────────────────────────────────────────────────────────────────


def _hm_to_dict(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]) if row["company_id"] else None,
        "full_name": row["full_name"],
        "title": row["title"],
        "email": row["email"] if row["email_verified"] else None,  # only expose verified email
        "email_verified": row["email_verified"],
        "linkedin_url": row["linkedin_url"],
        "enrich_status": row["enrich_status"],
        "last_enriched": row["last_enriched"].isoformat() if row["last_enriched"] else None,
        "created_at": row["created_at"].isoformat(),
    }
