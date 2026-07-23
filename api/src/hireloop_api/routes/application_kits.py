"""Application kit REST routes — list/fetch per-job apply assets."""

from __future__ import annotations

import uuid
from typing import Literal, cast

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.models.ai_operation import AiOperationAccepted
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
    ats = row["ats_report"] if "ats_report" in row.keys() else None
    dossier = row["dossier"] if "dossier" in row.keys() else None
    return {
        "id": str(row["id"]),
        "job_id": str(row["job_id"]),
        "job_title": row["job_title"],
        "company_name": row["company_name"],
        "cover_letter": row["cover_letter"],
        "interview_prep": row["interview_prep"],
        "tailored_resume_id": str(row["tailored_resume_id"]) if row["tailored_resume_id"] else None,
        "mock_interview_id": str(row["mock_interview_id"]) if row["mock_interview_id"] else None,
        "ats_report": dict(ats) if isinstance(ats, dict) else ats,
        "dossier": dict(dossier) if isinstance(dossier, dict) else dossier,
        "reviewer_notes": row.get("reviewer_notes"),
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _application_kit_job_key(candidate_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"application_kit:{candidate_id}:{job_id}"


async def _latest_application_kit_job(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
) -> asyncpg.Record | None:
    return await db.fetchrow(
        """
        SELECT id, status, last_error, attempts, max_attempts,
               created_at, updated_at, completed_at
        FROM public.background_jobs
        WHERE idempotency_key = $1
          AND kind = $2
        ORDER BY created_at DESC
        LIMIT 1
        """,
        _application_kit_job_key(candidate_id, job_id),
        background_jobs.APPLICATION_KIT,
    )


async def _active_application_kit_job_id(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
) -> uuid.UUID | None:
    job = await _latest_application_kit_job(db, candidate_id=candidate_id, job_id=job_id)
    if not job or job["status"] not in {"pending", "running"}:
        return None
    return uuid.UUID(str(job["id"]))


async def _application_kit_row_for_job(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
) -> asyncpg.Record | None:
    return await db.fetchrow(
        """
        SELECT k.id, k.job_id, k.cover_letter, k.interview_prep,
               k.tailored_resume_id, k.mock_interview_id,
               k.ats_report, k.dossier, k.reviewer_notes,
               k.created_at, k.updated_at,
               j.title AS job_title, co.name AS company_name
        FROM public.job_application_kits k
        JOIN public.jobs j ON j.id = k.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE k.candidate_id = $1::uuid AND k.job_id = $2::uuid
        """,
        candidate_id,
        job_id,
    )


def _serialize_background_job(row: asyncpg.Record | None) -> dict | None:
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
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
               k.tailored_resume_id, k.mock_interview_id,
               k.ats_report, k.dossier, k.reviewer_notes,
               k.created_at, k.updated_at,
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

    row = await _application_kit_row_for_job(db, candidate_id=cid, job_id=job_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="No application kit for this job yet")
    if not row["tailored_resume_id"] and await _active_application_kit_job_id(
        db,
        candidate_id=cid,
        job_id=job_uuid,
    ):
        raise HTTPException(status_code=404, detail="Application kit is still preparing")
    return {"kit": _serialize_kit(row)}


@router.get("/jobs/{job_id}/status")
async def get_application_kit_status_for_job(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Poll-friendly application-kit status, including durable job failures."""
    cid = await _candidate_id(db, current_user["id"])
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    row = await _application_kit_row_for_job(db, candidate_id=cid, job_id=job_uuid)
    job = await _latest_application_kit_job(db, candidate_id=cid, job_id=job_uuid)
    background_job = _serialize_background_job(job)
    job_status = job["status"] if job else None

    # Ready only when a tailored resume exists — cover/interview-only rows are incomplete.
    if row and row["tailored_resume_id"]:
        return {
            "status": "ready",
            "saved": True,
            "job_id": str(job_uuid),
            "kit": _serialize_kit(row),
            "background_job": background_job,
        }

    if job_status in {"pending", "running"}:
        return {
            "status": "processing",
            "saved": bool(row),
            "job_id": str(job_uuid),
            "background_job": background_job,
            "message": "Preparing your resume, cover letter, and interview prep.",
        }

    if job_status == "failed":
        return {
            "status": "failed",
            "saved": bool(row),
            "job_id": str(job_uuid),
            "background_job": background_job,
            "message": "Application kit generation failed. Please retry from the job card.",
        }

    if job_status == "completed" and (not row or not row["tailored_resume_id"]):
        return {
            "status": "failed",
            "saved": bool(row),
            "job_id": str(job_uuid),
            "background_job": background_job,
            "message": "Application kit generation finished without creating a resume. Please retry.",
        }

    # Incomplete kit row (cover/prep, no resume) and no active job — treat as missing
    # so clients can POST /prepare again instead of stopping on a hollow "ready".
    return {
        "status": "missing",
        "saved": bool(row),
        "job_id": str(job_uuid),
        "background_job": background_job,
        "message": "No application kit for this job yet.",
    }


@router.post("/jobs/{job_id}/prepare")
async def prepare_application_kit_for_job(
    job_id: str,
    response: Response,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict | AiOperationAccepted:
    """Queue resume, cover letter, and interview prep generation for one job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    cid = await _candidate_id(db, current_user["id"])
    existing = await _application_kit_row_for_job(db, candidate_id=cid, job_id=job_uuid)
    if existing and existing["tailored_resume_id"]:
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

    try:
        from hireloop_api.services.ai_operations import enqueue_ai_operation_outcome

        async with db.transaction():
            await db.execute(
                """
                INSERT INTO public.saved_jobs (candidate_id, job_id)
                VALUES ($1::uuid, $2::uuid)
                ON CONFLICT (candidate_id, job_id) DO NOTHING
                """,
                cid,
                job_uuid,
            )
            outcome = await enqueue_ai_operation_outcome(
                db,
                user_id=uuid.UUID(str(current_user["id"])),
                candidate_id=cid,
                kind=background_jobs.APPLICATION_KIT,
                payload={"candidate_id": str(cid), "job_id": str(job_uuid)},
                idempotency_key=_application_kit_job_key(cid, job_uuid),
                resource_type="job",
                resource_id=job_uuid,
                stage="queued",
                message="Your application kit is queued.",
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

    response.status_code = 202
    operation = outcome.operation
    if operation.status not in {"queued", "running"}:
        raise RuntimeError("Enqueued application kit operation is not active")
    return AiOperationAccepted(
        operation_id=operation.id,
        status=cast(Literal["queued", "running"], operation.status),
        status_url=f"/api/v1/ai-operations/{operation.id}",
    )
