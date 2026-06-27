"""
Tailored resume routes (P20).
"""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_india_verified_user
from hireloop_api.services.rate_limit import check_rate_limit
from hireloop_api.services.resume_tailor import generate_tailored_html, save_tailored_resume

logger = structlog.get_logger()
router = APIRouter(prefix="/tailored-resumes", tags=["resumes-tailor"])


class TailorRequest(BaseModel):
    job_id: uuid.UUID
    template: str = Field(default="modern", pattern="^(modern|classic|minimal)$")


async def _run_tailor_task(
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    template: str,
    settings: Settings,
) -> None:
    from hireloop_api.deps import get_db_pool

    pool = await get_db_pool(settings)
    async with pool.acquire() as db:
        cand = await db.fetchrow(
            """
            SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
                   c.skills, c.years_experience, u.full_name, u.email
            FROM public.candidates c
            JOIN public.users u ON u.id = c.user_id
            WHERE c.id = $1
            """,
            candidate_id,
        )
        job = await db.fetchrow(
            """
            SELECT j.id, j.title, j.description, j.requirements, j.skills_required,
                   co.name AS company_name
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.id = $1
            """,
            job_id,
        )
        if not cand or not job:
            return

        llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=4096,  # resumes can be long
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Resume Tailor",
            },
        )
        profile = dict(cand)
        job_d = dict(job)
        try:
            html = await generate_tailored_html(
                llm=llm,
                candidate_profile=profile,
                job=job_d,
                template=template,
            )
            summary = html.split("<p>", 2)[1][:200] if "<p>" in html else ""
            await save_tailored_resume(
                db,
                candidate_id=candidate_id,
                job_id=job_id,
                template=template,
                html_content=html,
                summary_line=summary,
            )
        except Exception as exc:
            logger.error("tailor_failed", error=str(exc))
            await db.execute(
                """
                INSERT INTO public.tailored_resumes
                  (candidate_id, job_id, template, file_path, status, error_message)
                VALUES ($1, $2, $3, 'failed', 'failed', $4)
                ON CONFLICT (candidate_id, job_id) DO UPDATE SET
                  status = 'failed', error_message = $4
                """,
                candidate_id,
                job_id,
                template,
                str(exc)[:500],
            )


@router.post("/tailor")
async def request_tailored_resume(
    body: TailorRequest,
    current_user: dict = Depends(get_india_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    # #48: each tailor run is a multi-call LLM job — cap per user per hour.
    check_rate_limit(str(current_user["id"]), "tailor_resume", max_per_hour=10)

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        current_user["id"],
    )
    if not candidate:
        raise HTTPException(404, "Candidate profile required")

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

    row = await db.fetchrow(
        """
        INSERT INTO public.tailored_resumes (candidate_id, job_id, template, file_path, status)
        VALUES ($1, $2, $3, 'pending', 'processing')
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          status = 'processing', template = EXCLUDED.template
        RETURNING id
        """,
        candidate["id"],
        body.job_id,
        body.template,
    )
    resume_id = str(row["id"]) if row else None

    from hireloop_api.services.background_jobs import TAILORED_RESUME, enqueue_job

    await enqueue_job(
        db,
        kind=TAILORED_RESUME,
        payload={
            "candidate_id": str(candidate["id"]),
            "job_id": str(body.job_id),
            "template": body.template,
        },
        idempotency_key=f"tailored_resume:{candidate['id']}:{body.job_id}",
    )
    return {
        "status": "processing",
        "resume_id": resume_id,
        "message": "Tailoring started — poll in ~30s",
    }


@router.get("/tailored")
async def list_tailored_resumes(
    current_user: dict = Depends(get_india_verified_user),
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
    current_user: dict = Depends(get_india_verified_user),
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
    print_dialog: bool = True,
    current_user: dict = Depends(get_india_verified_user),
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

    # Wrap the LLM body in a print-ready A4 document and auto-open the browser's
    # print dialog, so "download" yields a clean PDF via Save as PDF (no headless
    # browser dependency). document.title seeds the suggested PDF filename.
    from hireloop_api.services.resume_tailor import wrap_print_document

    name = (row["full_name"] or "").strip()
    title = f"{name} — Resume" if name else "Resume"
    # print_dialog=False is used by the in-app preview (rendered in an iframe),
    # where auto-opening the browser print dialog would be disruptive.
    html_doc = wrap_print_document(row["html_content"], title=title, auto_print=print_dialog)
    return Response(
        content=html_doc,
        media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="resume-{resume_id}.html"'},
    )
