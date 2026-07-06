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
from hireloop_api.services.profile_experience import (
    build_merged_education,
    build_merged_experience,
)
from hireloop_api.services.resume_tailor import generate_path_resume_html

logger = structlog.get_logger()


async def _load_candidate_profile(
    db: asyncpg.Connection, candidate_id: str
) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, c.linkedin_url, c.linkedin_data, c.career_profile,
               u.full_name, u.email, u.phone
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(candidate_id),
    )
    if not row:
        return None
    data = dict(row)
    data["skills"] = list(data.get("skills") or [])
    career_profile = (
        data.get("career_profile") if isinstance(data.get("career_profile"), dict) else None
    )
    experience = build_merged_experience(
        resume_experience=[],
        linkedin_data=data.get("linkedin_data"),
        career_profile=career_profile,
        career_intelligence=None,
        candidate=data,
        skills=data["skills"],
    )
    education = build_merged_education(
        resume_education=[],
        linkedin_data=data.get("linkedin_data"),
        career_profile=career_profile,
    )
    return {
        "full_name": data.get("full_name"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "headline": data.get("headline"),
        "summary": data.get("summary"),
        "current_title": data.get("current_title"),
        "current_company": data.get("current_company"),
        "years_experience": data.get("years_experience"),
        "location_city": data.get("location_city"),
        "location_state": data.get("location_state"),
        "skills": data["skills"],
        "looking_for": data.get("looking_for"),
        "linkedin_url": data.get("linkedin_url"),
        "experience": experience[:10],
        "education": education[:6],
    }


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
