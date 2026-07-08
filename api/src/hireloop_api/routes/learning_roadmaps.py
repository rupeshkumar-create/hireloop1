"""
Learning roadmap routes.

Per-job, AI-generated personal learning plan rendered as a self-contained
interactive HTML app. Mirrors the tailored-resume request/poll/download flow.
"""

from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.services.learning_roadmap import (
    generate_roadmap,
    render_roadmap_html,
    save_learning_roadmap,
)
from hireloop_api.services.rate_limit import check_rate_limit

logger = structlog.get_logger()
router = APIRouter(prefix="/learning-roadmaps", tags=["learning-roadmaps"])


class RoadmapRequest(BaseModel):
    job_id: uuid.UUID


async def _run_roadmap_task(
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
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
            WHERE j.id = $1 AND j.deleted_at IS NULL
            """,
            job_id,
        )
        if not cand or not job:
            return

        llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.4,
            max_tokens=4096,
            default_headers={
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Learning Roadmap",
            },
        )
        profile = dict(cand)
        job_d = dict(job)
        try:
            roadmap = await generate_roadmap(llm=llm, candidate_profile=profile, job=job_d)
            html_doc = render_roadmap_html(
                roadmap,
                job_title=str(job_d.get("title") or "this role"),
                company_name=str(job_d.get("company_name") or ""),
                candidate_name=str(cand["full_name"] or "You"),
                storage_key=str(job_id),
            )
            summary = str(roadmap.get("summary") or "")[:200]
            await save_learning_roadmap(
                db,
                candidate_id=candidate_id,
                job_id=job_id,
                html_content=html_doc,
                summary_line=summary,
            )
        except Exception as exc:
            logger.error("roadmap_failed", error=str(exc))
            await db.execute(
                """
                INSERT INTO public.learning_roadmaps
                  (candidate_id, job_id, file_path, status, error_message)
                VALUES ($1, $2, 'failed', 'failed', $3)
                ON CONFLICT (candidate_id, job_id) DO UPDATE SET
                  status = 'failed', error_message = $3
                """,
                candidate_id,
                job_id,
                str(exc)[:500],
            )


@router.post("/roadmap")
async def request_learning_roadmap(
    body: RoadmapRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    # Each roadmap is an LLM job — cap per user per hour.
    check_rate_limit(str(current_user["id"]), "learning_roadmap", max_per_hour=10)

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        current_user["id"],
    )
    if not candidate:
        raise HTTPException(404, "Candidate profile required")

    existing = await db.fetchrow(
        """
        SELECT id FROM public.learning_roadmaps
        WHERE candidate_id = $1 AND job_id = $2 AND status = 'ready'
          AND expires_at > NOW()
        """,
        candidate["id"],
        body.job_id,
    )
    if existing:
        return {
            "roadmap_id": str(existing["id"]),
            "status": "ready",
            "download_path": f"/api/v1/learning-roadmaps/{existing['id']}",
        }

    row = await db.fetchrow(
        """
        INSERT INTO public.learning_roadmaps (candidate_id, job_id, file_path, status)
        VALUES ($1, $2, 'pending', 'processing')
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET status = 'processing'
        RETURNING id
        """,
        candidate["id"],
        body.job_id,
    )
    roadmap_id = str(row["id"]) if row else None

    from hireloop_api.services.background_jobs import LEARNING_ROADMAP, enqueue_job

    await enqueue_job(
        db,
        kind=LEARNING_ROADMAP,
        payload={
            "candidate_id": str(candidate["id"]),
            "job_id": str(body.job_id),
        },
        idempotency_key=f"learning_roadmap:{candidate['id']}:{body.job_id}",
    )
    return {
        "status": "processing",
        "roadmap_id": roadmap_id,
        "message": "Building your roadmap — poll in ~30s",
    }


@router.get("/roadmaps")
async def list_learning_roadmaps(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT lr.id, lr.job_id, lr.status, lr.summary_line,
               lr.created_at, lr.expires_at, j.title AS job_title
        FROM public.learning_roadmaps lr
        JOIN public.candidates c ON c.id = lr.candidate_id
        JOIN public.jobs j ON j.id = lr.job_id
        WHERE c.user_id = $1
        ORDER BY lr.created_at DESC
        """,
        current_user["id"],
    )
    return [dict(r) for r in rows]


@router.get("/{roadmap_id}")
async def get_learning_roadmap(
    roadmap_id: uuid.UUID,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await db.fetchrow(
        """
        SELECT lr.id, lr.file_path, lr.status, lr.summary_line, lr.expires_at
        FROM public.learning_roadmaps lr
        JOIN public.candidates c ON c.id = lr.candidate_id
        WHERE lr.id = $1 AND c.user_id = $2
        """,
        roadmap_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(404, "Roadmap not found")
    if row["status"] != "ready":
        return dict(row)
    return {
        **dict(row),
        "download_url": f"/api/v1/learning-roadmaps/{roadmap_id}/download",
    }


@router.get("/{roadmap_id}/download")
async def download_learning_roadmap(
    roadmap_id: uuid.UUID,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    row = await db.fetchrow(
        """
        SELECT lr.html_content
        FROM public.learning_roadmaps lr
        JOIN public.candidates c ON c.id = lr.candidate_id
        WHERE lr.id = $1 AND c.user_id = $2 AND lr.status = 'ready'
        """,
        roadmap_id,
        current_user["id"],
    )
    if not row or not row["html_content"]:
        raise HTTPException(404, "Roadmap not ready")
    return Response(
        content=row["html_content"],
        media_type="text/html",
        headers={"Content-Disposition": f'inline; filename="roadmap-{roadmap_id}.html"'},
    )
