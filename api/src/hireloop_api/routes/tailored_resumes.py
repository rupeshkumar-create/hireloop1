"""
Tailored resume routes (P20).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal, cast

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.models.ai_operation import AiOperationAccepted
from hireloop_api.services.rate_limit import check_rate_limit
from hireloop_api.services.tailored_resume_settings import tailored_resume_enabled

router = APIRouter(prefix="/tailored-resumes", tags=["resumes-tailor"])


class TailorRequest(BaseModel):
    job_id: uuid.UUID
    template: str = Field(default="modern", pattern="^(modern|classic|minimal)$")


@router.post("/tailor")
async def request_tailored_resume(
    body: TailorRequest,
    response: Response,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict | AiOperationAccepted:

    candidate = await db.fetchrow(
        """
        SELECT id, tailored_resume_enabled
        FROM public.candidates
        WHERE user_id = $1 AND deleted_at IS NULL
        """,
        current_user["id"],
    )
    if not candidate:
        raise HTTPException(404, "Candidate profile required")
    if not tailored_resume_enabled(candidate):
        raise HTTPException(
            status_code=403,
            detail="Enable tailored resumes in Settings before generating role-specific resumes.",
        )

    existing = await db.fetchrow(
        """
        SELECT id, status, file_path, expires_at
        FROM public.tailored_resumes
        WHERE candidate_id = $1 AND job_id = $2 AND status = 'ready'
          AND expires_at > NOW()
        """,
        candidate["id"],
        body.job_id,
    )
    if existing:
        return {
            "resume_id": str(existing["id"]),
            "status": "ready",
            "download_path": f"/api/v1/tailored-resumes/tailored/{existing['id']}",
        }

    from hireloop_api.services.ai_operations import enqueue_ai_operation_outcome
    from hireloop_api.services.background_jobs import TAILORED_RESUME

    user_id = uuid.UUID(str(current_user["id"]))
    candidate_id = uuid.UUID(str(candidate["id"]))
    async with db.transaction():
        row = await db.fetchrow(
            """
            INSERT INTO public.tailored_resumes (candidate_id, job_id, template, file_path, status)
            VALUES ($1, $2, $3, 'pending', 'processing')
            ON CONFLICT (candidate_id, job_id) DO NOTHING
            RETURNING id, status
            """,
            candidate_id,
            body.job_id,
            body.template,
        )
        if row is None:
            row = await db.fetchrow(
                """
                SELECT id, status, expires_at FROM public.tailored_resumes
                WHERE candidate_id = $1 AND job_id = $2
                """,
                candidate_id,
                body.job_id,
            )
        if row is None:
            raise RuntimeError("Tailored resume row could not be created")
        resume_id = uuid.UUID(str(row["id"]))
        if (
            row["status"] == "ready"
            and row.get("expires_at")
            and row["expires_at"] > datetime.now(UTC)
        ):
            return {
                "resume_id": str(resume_id),
                "status": "ready",
                "download_path": f"/api/v1/tailored-resumes/tailored/{resume_id}",
            }
        # Expired ready / failed / processing rows must flip to processing while regenerating.
        await db.execute(
            """
            UPDATE public.tailored_resumes
            SET status = 'processing', template = $3, error_message = NULL
            WHERE candidate_id = $1 AND job_id = $2
            """,
            candidate_id,
            body.job_id,
            body.template,
        )
        outcome = await enqueue_ai_operation_outcome(
            db,
            user_id=user_id,
            candidate_id=candidate_id,
            kind=TAILORED_RESUME,
            payload={
                "candidate_id": str(candidate_id),
                "job_id": str(body.job_id),
                "template": body.template,
                "resume_id": str(resume_id),
            },
            idempotency_key=f"tailored_resume:{candidate_id}:{body.job_id}",
            resource_type="tailored_resume",
            resource_id=resume_id,
            stage="queued",
            message="Your tailored resume is queued.",
        )
        if outcome.created:
            await check_rate_limit(str(user_id), "tailor_resume", max_per_hour=10, db=db)

    response.status_code = 202
    operation = outcome.operation
    return AiOperationAccepted(
        operation_id=operation.id,
        status=cast(Literal["queued", "running"], operation.status),
        status_url=f"/api/v1/ai-operations/{operation.id}",
    )


@router.get("/tailored")
async def list_tailored_resumes(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT tr.id, tr.job_id, tr.template, tr.status, tr.summary_line,
               tr.created_at, tr.expires_at, j.title AS job_title
        FROM public.tailored_resumes tr
        JOIN public.candidates c ON c.id = tr.candidate_id
        JOIN public.jobs j ON j.id = tr.job_id
        WHERE c.user_id = $1
        ORDER BY tr.created_at DESC
        """,
        current_user["id"],
    )
    return [dict(r) for r in rows]


@router.get("/tailored/{resume_id}")
async def get_tailored_resume(
    resume_id: uuid.UUID,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await db.fetchrow(
        """
        SELECT tr.id, tr.file_path, tr.status, tr.template, tr.summary_line, tr.expires_at
        FROM public.tailored_resumes tr
        JOIN public.candidates c ON c.id = tr.candidate_id
        WHERE tr.id = $1 AND c.user_id = $2
        """,
        resume_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(404, "Resume not found")
    if row["status"] != "ready":
        return dict(row)
    # HTML stored at file_path key — return signed URL pattern for client
    return {
        **dict(row),
        "download_url": f"/api/v1/tailored-resumes/tailored/{resume_id}/download",
    }


@router.get("/tailored/{resume_id}/download")
async def download_tailored_resume(
    resume_id: uuid.UUID,
    file_format: str = Query(default="html", alias="format", pattern="^(html|pdf|docx)$"),
    print_dialog: bool = True,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    row = await db.fetchrow(
        """
        SELECT tr.html_content, u.full_name
        FROM public.tailored_resumes tr
        JOIN public.candidates c ON c.id = tr.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE tr.id = $1 AND c.user_id = $2 AND tr.status = 'ready'
        """,
        resume_id,
        current_user["id"],
    )
    if not row or not row["html_content"]:
        raise HTTPException(404, "Resume not ready")

    name = (row["full_name"] or "").strip()
    title = f"{name} — Resume" if name else "Resume"

    if file_format == "docx":
        from hireloop_api.services.resume_export import html_resume_to_docx

        docx_bytes = html_resume_to_docx(row["html_content"], title=title)
        safe = (name or "resume").replace(" ", "_")
        return Response(
            content=docx_bytes,
            media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            headers={"Content-Disposition": f'attachment; filename="{safe}_resume.docx"'},
        )

    # Wrap the LLM body in a print-ready A4 document and auto-open the browser's
    # print dialog, so "download" yields a clean PDF via Save as PDF (no headless
    # browser dependency). document.title seeds the suggested PDF filename.
    from hireloop_api.services.resume_tailor import wrap_print_document

    # print_dialog=False is used by the in-app preview (rendered in an iframe),
    # where auto-opening the browser print dialog would be disruptive.
    auto_print = file_format == "pdf" or print_dialog
    html_doc = wrap_print_document(row["html_content"], title=title, auto_print=auto_print)
    return Response(
        content=html_doc,
        media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="resume-{resume_id}.html"'},
    )
