"""Application kit REST routes — list/fetch per-job apply assets."""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.services import background_jobs

logger = structlog.get_logger()
router = APIRouter(prefix="/application-kits", tags=["application-kits"])


async def _candidate_id(db: asyncpg.Connection, user_id: str) -> uuid.UUID:
    row = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Complete your profile first")
    return row["id"]


def _serialize_kit(row: asyncpg.Record) -> dict:
    return {
        "id": str(row["id"]),
        "job_id": str(row["job_id"]),
        "job_title": row.get("job_title"),
        "company_name": row.get("company_name"),
        "cover_letter": row["cover_letter"],
        "interview_prep": row["interview_prep"],
        "tailored_resume_id": str(row["tailored_resume_id"]) if row["tailored_resume_id"] else None,
        "mock_interview_id": str(row["mock_interview_id"]) if row["mock_interview_id"] else None,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.get("")
async def list_application_kits(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    limit: int = 50,
) -> dict:
    """All application kits for the signed-in candidate."""
    cid = await _candidate_id(db, current_user["id"])
    rows = await db.fetch(
        """
        SELECT k.id, k.job_id, k.cover_letter, k.interview_prep,
               k.tailored_resume_id, k.mock_interview_id, k.created_at, k.updated_at,
               j.title AS job_title, co.name AS company_name
        FROM public.job_application_kits k
        JOIN public.jobs j ON j.id = k.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE k.candidate_id = $1::uuid
        ORDER BY k.updated_at DESC
        LIMIT $2
        """,
        cid,
        min(limit, 100),
    )
    return {"kits": [_serialize_kit(r) for r in rows]}


@router.get("/jobs/{job_id}")
async def get_application_kit_for_job(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Single application kit for a candidate + job pair."""
    cid = await _candidate_id(db, current_user["id"])
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    row = await db.fetchrow(
        """
        SELECT k.id, k.job_id, k.cover_letter, k.interview_prep,
               k.tailored_resume_id, k.mock_interview_id, k.created_at, k.updated_at,
               j.title AS job_title, co.name AS company_name
        FROM public.job_application_kits k
        JOIN public.jobs j ON j.id = k.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE k.candidate_id = $1::uuid AND k.job_id = $2::uuid
        """,
        cid,
        job_uuid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="No application kit for this job yet")
    return {"kit": _serialize_kit(row)}


@router.post("/jobs/{job_id}/prepare")
async def prepare_application_kit_for_job(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Queue resume, cover letter, and interview prep generation for one job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    cid = await _candidate_id(db, current_user["id"])
    existing = await db.fetchrow(
        """
        SELECT k.id, k.job_id, k.cover_letter, k.interview_prep,
               k.tailored_resume_id, k.mock_interview_id, k.created_at, k.updated_at,
               j.title AS job_title, co.name AS company_name
        FROM public.job_application_kits k
        JOIN public.jobs j ON j.id = k.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE k.candidate_id = $1::uuid AND k.job_id = $2::uuid
        """,
        cid,
        job_uuid,
    )
    if existing:
        return {"status": "ready", "saved": True, "kit": _serialize_kit(existing)}

    job = await db.fetchrow(
        """
        SELECT id FROM public.jobs
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        job_uuid,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.execute(
        """
        INSERT INTO public.saved_jobs (candidate_id, job_id)
        VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (candidate_id, job_id) DO NOTHING
        """,
        cid,
        job_uuid,
    )

    try:
        background_job_id = await background_jobs.enqueue_job(
            db,
            kind=background_jobs.APPLICATION_KIT,
            payload={"candidate_id": str(cid), "job_id": str(job_uuid)},
            idempotency_key=f"application_kit:{cid}:{job_uuid}",
            max_attempts=3,
        )
    except Exception as exc:
        logger.exception(
            "application_kit_enqueue_failed",
            job_id=job_id,
            user_id=str(current_user.get("id")),
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=502,
            detail="Couldn't start the application kit. Please try again in a moment.",
        ) from exc

    return {
        "status": "processing",
        "saved": True,
        "job_id": str(job_uuid),
        "background_job_id": str(background_job_id),
        "message": "Preparing your resume, cover letter, and interview prep.",
    }
