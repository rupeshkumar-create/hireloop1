"""Shared helpers for saved jobs, applications, and the candidate job tracker."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from hireloop_api.config import Settings, get_settings


async def ensure_saved_job(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    """Bookmark a job for the candidate (idempotent)."""
    await db.execute(
        """
        INSERT INTO public.saved_jobs (candidate_id, job_id)
        VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (candidate_id, job_id) DO NOTHING
        """,
        candidate_id,
        job_id,
    )


async def record_direct_application(
    db: asyncpg.Connection,
    *,
    user_id: str,
    job_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Save the job and log a direct application (candidate clicked Apply).
    Idempotent per (candidate_id, job_id).
    """
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not candidate:
        return {"error": "Candidate profile not found"}

    job_uuid = uuid.UUID(job_id)
    candidate_id = candidate["id"]

    job_exists = await db.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM public.jobs WHERE id = $1::uuid AND deleted_at IS NULL
        )
        """,
        job_uuid,
    )
    if not job_exists:
        return {"error": "Job not found"}

    await ensure_saved_job(db, candidate_id, job_uuid)

    app_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.job_applications
          (id, candidate_id, job_id, apply_type, status, applied_at)
        VALUES ($1::uuid, $2::uuid, $3::uuid, 'direct', 'applied', NOW())
        ON CONFLICT (candidate_id, job_id) DO NOTHING
        """,
        app_id,
        candidate_id,
        job_uuid,
    )

    existing_id = await db.fetchval(
        """
        SELECT id FROM public.job_applications
        WHERE candidate_id = $1::uuid AND job_id = $2::uuid
        """,
        candidate_id,
        job_uuid,
    )

    job_row = await db.fetchrow(
        """
        SELECT j.title, co.name AS company_name
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.id = $1::uuid
        """,
        job_uuid,
    )
    if job_row:
        from hireloop_api.services.notifications import notify_application_update

        cfg = settings or get_settings()
        await notify_application_update(
            db,
            cfg,
            candidate_user_id=user_id,
            job_id=job_id,
            job_title=job_row["title"] or "Role",
            company_name=job_row["company_name"],
            status="applied",
        )

    return {
        "application_id": str(existing_id or app_id),
        "job_id": job_id,
        "saved": True,
        "applied": True,
        "status": "applied",
    }
