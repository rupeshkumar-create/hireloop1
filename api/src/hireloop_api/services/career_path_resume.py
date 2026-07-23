"""Generate tailored resumes for each career-path direction (up to 3)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings
from hireloop_api.services.career_path import CareerPathService
from hireloop_api.services.career_path_selection import career_path_options
from hireloop_api.services.resume_tailor import generate_path_resume_html
from hireloop_api.services.tailored_resume_profile import load_tailored_resume_profile
from hireloop_api.services.tailored_resume_settings import fetch_tailored_resume_enabled

logger = structlog.get_logger()

ProgressCallback = Callable[[int, str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PreparedPathResume:
    id: uuid.UUID
    title: str
    html: str


@dataclass(frozen=True, slots=True)
class PreparedPathResumeBatch:
    candidate_id: uuid.UUID
    career_path_id: uuid.UUID | None
    resumes: tuple[PreparedPathResume, ...]


async def list_path_resumes(db: asyncpg.Connection, candidate_id: str) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """
        SELECT id, path_title, status, created_at, updated_at
        FROM public.career_path_resumes
        WHERE candidate_id = $1::uuid
        ORDER BY updated_at DESC
        """,
        uuid.UUID(candidate_id),
    )
    return [
        {
            "id": str(r["id"]),
            "path_title": r["path_title"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "preview_path": (
                f"/api/v1/career/path-resumes/{r['id']}/download?format=html&print_dialog=false"
                if r["status"] == "ready"
                else None
            ),
            "download_path": (
                f"/api/v1/career/path-resumes/{r['id']}/download?format=pdf"
                if r["status"] == "ready"
                else None
            ),
            "docx_path": (
                f"/api/v1/career/path-resumes/{r['id']}/download?format=docx"
                if r["status"] == "ready"
                else None
            ),
        }
        for r in rows
    ]


async def generate_path_resumes(
    db: asyncpg.Connection,
    candidate_id: str,
    settings: Settings,
) -> list[dict[str, Any]]:
    if not await fetch_tailored_resume_enabled(db, uuid.UUID(candidate_id)):
        raise ValueError(
            "Enable tailored resumes in Settings before generating path-specific resumes."
        )

    if not settings.openrouter_api_key:
        raise ValueError("Resume generation is temporarily unavailable.")

    path = await CareerPathService.get_latest(db, candidate_id)
    if not path:
        raise ValueError("Generate your career path first.")

    titles = career_path_options(path)
    if not titles:
        raise ValueError("No career path directions to generate resumes for.")

    profile = await load_tailored_resume_profile(db, uuid.UUID(candidate_id))
    if not profile:
        raise ValueError("Candidate profile not found.")

    llm = ChatOpenAI(
        model=settings.openrouter_primary_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.25,
    )

    path_id = path.get("id")
    path_summary = path.get("summary")
    results: list[dict[str, Any]] = []

    for title in titles:
        await db.execute(
            """
            INSERT INTO public.career_path_resumes
              (candidate_id, career_path_id, path_title, status)
            VALUES ($1::uuid, $2::uuid, $3, 'generating')
            ON CONFLICT (candidate_id, path_title) DO UPDATE SET
              status = 'generating',
              updated_at = NOW()
            """,
            uuid.UUID(candidate_id),
            uuid.UUID(str(path_id)) if path_id else None,
            title,
        )
        try:
            html = await generate_path_resume_html(
                llm=llm,
                candidate_profile=profile,
                path_title=title,
                path_summary=str(path_summary) if path_summary else None,
            )
            row = await db.fetchrow(
                """
                UPDATE public.career_path_resumes
                SET html_content = $3, status = 'ready', updated_at = NOW()
                WHERE candidate_id = $1::uuid AND path_title = $2
                RETURNING id, path_title, status, updated_at
                """,
                uuid.UUID(candidate_id),
                title,
                html[:500_000],
            )
            if row:
                rid = str(row["id"])
                results.append(
                    {
                        "id": rid,
                        "path_title": row["path_title"],
                        "status": row["status"],
                        "preview_path": f"/api/v1/career/path-resumes/{rid}/download?format=html&print_dialog=false",
                        "download_path": f"/api/v1/career/path-resumes/{rid}/download?format=pdf",
                        "docx_path": f"/api/v1/career/path-resumes/{rid}/download?format=docx",
                    }
                )
        except Exception as exc:
            logger.warning(
                "career_path_resume_failed",
                candidate_id=candidate_id,
                title=title,
                error=str(exc)[:200],
            )
            await db.execute(
                """
                UPDATE public.career_path_resumes
                SET status = 'failed', updated_at = NOW()
                WHERE candidate_id = $1::uuid AND path_title = $2
                """,
                uuid.UUID(candidate_id),
                title,
            )

    return results or await list_path_resumes(db, candidate_id)


async def prepare_path_resumes(
    pool: asyncpg.Pool,
    candidate_id: str,
    settings: Settings,
    on_progress: ProgressCallback | None = None,
) -> PreparedPathResumeBatch:
    """Load inputs briefly, then generate resumes without holding a DB lease."""

    async def _progress(percent: int, stage: str, message: str) -> None:
        if on_progress is not None:
            await on_progress(percent, stage, message)

    candidate_uuid = uuid.UUID(candidate_id)
    await _progress(10, "profile", "Loading your profile.")
    async with pool.acquire() as db:
        if not await fetch_tailored_resume_enabled(db, candidate_uuid):
            raise ValueError(
                "Enable tailored resumes in Settings before generating path-specific resumes."
            )
        path = await CareerPathService.get_latest(db, candidate_id)
        profile = await load_tailored_resume_profile(db, candidate_uuid)
    if not settings.openrouter_api_key:
        raise ValueError("Resume generation is temporarily unavailable.")
    if not path:
        raise ValueError("Generate your career path first.")
    titles = career_path_options(path)
    if not titles:
        raise ValueError("No career path directions to generate resumes for.")
    if not profile:
        raise ValueError("Candidate profile not found.")

    llm = ChatOpenAI(
        model=settings.openrouter_primary_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.25,
    )
    prepared: list[PreparedPathResume] = []
    total = len(titles)
    for index, title in enumerate(titles):
        # Bound progress between 35 and 75 across path titles (monotonic).
        percent = 35 + int((index / max(total, 1)) * 40)
        await _progress(percent, "resume", "Preparing your career-path resumes.")
        html = await generate_path_resume_html(
            llm=llm,
            candidate_profile=profile,
            path_title=title,
            path_summary=str(path.get("summary")) if path.get("summary") else None,
        )
        prepared.append(PreparedPathResume(id=uuid.uuid4(), title=title, html=html))
    await _progress(80, "finalizing", "Finalizing your career-path resumes.")
    path_id = path.get("id")
    return PreparedPathResumeBatch(
        candidate_id=candidate_uuid,
        career_path_id=uuid.UUID(str(path_id)) if path_id else None,
        resumes=tuple(prepared),
    )


async def persist_prepared_path_resumes(
    db: asyncpg.Connection, prepared: PreparedPathResumeBatch
) -> None:
    for resume in prepared.resumes:
        await db.execute(
            """
            INSERT INTO public.career_path_resumes
              (id, candidate_id, career_path_id, path_title, html_content, status)
            VALUES ($1, $2, $3, $4, $5, 'ready')
            ON CONFLICT (candidate_id, path_title) DO UPDATE SET
              career_path_id = EXCLUDED.career_path_id,
              html_content = EXCLUDED.html_content,
              status = 'ready',
              updated_at = NOW()
            """,
            resume.id,
            prepared.candidate_id,
            prepared.career_path_id,
            resume.title,
            resume.html[:500_000],
        )


async def fetch_path_resume_html(
    db: asyncpg.Connection,
    *,
    resume_id: str,
    candidate_id: str,
) -> tuple[str | None, str | None]:
    """Return (html_fragment, path_title) for the owner only — not public."""
    row = await db.fetchrow(
        """
        SELECT path_title, html_content
        FROM public.career_path_resumes
        WHERE id = $1::uuid AND candidate_id = $2::uuid AND status = 'ready'
        """,
        uuid.UUID(resume_id),
        uuid.UUID(candidate_id),
    )
    if not row or not row["html_content"]:
        return None, None
    return str(row["html_content"]), str(row["path_title"])
