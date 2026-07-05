"""Generate tailored resumes for each career-path direction (up to 3)."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings
from hireloop_api.services.career_path import CareerPathService
from hireloop_api.services.career_path_selection import career_path_options
from hireloop_api.services.resume_tailor import generate_tailored_html

logger = structlog.get_logger()


async def _load_candidate_profile(
    db: asyncpg.Connection, candidate_id: str
) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(candidate_id),
    )
    if not row:
        return None
    data = dict(row)
    data["skills"] = list(data.get("skills") or [])
    return data


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
            "download_path": (
                f"/api/v1/career/path-resumes/{r['id']}/download"
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
    if not settings.openrouter_api_key:
        raise ValueError("Resume generation is temporarily unavailable.")

    path = await CareerPathService.get_latest(db, candidate_id)
    if not path:
        raise ValueError("Generate your career path first.")

    titles = career_path_options(path)
    if not titles:
        raise ValueError("No career path directions to generate resumes for.")

    profile = await _load_candidate_profile(db, candidate_id)
    if not profile:
        raise ValueError("Candidate profile not found.")

    llm = ChatOpenAI(
        model=settings.openrouter_primary_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.3,
    )

    path_id = path.get("id")
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
        virtual_job = {
            "title": title,
            "company_name": "Target role",
            "description": (
                f"Career direction: {title}. "
                f"Candidate is positioning for this next-step role based on their "
                f"profile and career path on Hireloop."
            ),
        }
        try:
            html = await generate_tailored_html(
                llm=llm,
                candidate_profile=profile,
                job=virtual_job,
                template="modern",
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
                results.append(
                    {
                        "id": str(row["id"]),
                        "path_title": row["path_title"],
                        "status": row["status"],
                        "download_path": f"/api/v1/career/path-resumes/{row['id']}/download",
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


async def fetch_path_resume_html(
    db: asyncpg.Connection,
    *,
    resume_id: str,
    candidate_id: str | None = None,
    public_slug: str | None = None,
) -> str | None:
    """Owner download, or public download when profile is published."""
    if public_slug:
        row = await db.fetchrow(
            """
            SELECT cpr.html_content
            FROM public.career_path_resumes cpr
            JOIN public.candidates c ON c.id = cpr.candidate_id
            WHERE cpr.id = $1::uuid
              AND c.public_slug = $2
              AND c.public_profile_enabled = TRUE
              AND c.hide_contact_public = FALSE
              AND cpr.status = 'ready'
              AND c.deleted_at IS NULL
            """,
            uuid.UUID(resume_id),
            public_slug,
        )
    else:
        row = await db.fetchrow(
            """
            SELECT html_content FROM public.career_path_resumes
            WHERE id = $1::uuid AND candidate_id = $2::uuid AND status = 'ready'
            """,
            uuid.UUID(resume_id),
            uuid.UUID(candidate_id or ""),
        )
    if not row or not row["html_content"]:
        return None
    return str(row["html_content"])
