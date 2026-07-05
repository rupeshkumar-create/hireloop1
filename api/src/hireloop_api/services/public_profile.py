"""Public candidate profile — world-readable when published."""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Any

import asyncpg

from hireloop_api.services.display_name import pick_display_name
from hireloop_api.services.display_currency import currency_fields_for_candidate
from hireloop_api.services.profile_experience import (
    build_merged_education,
    build_merged_experience,
)


def _slug_base(name: str | None) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (name or "candidate").lower()).strip("-")
    return (raw[:28] or "candidate").strip("-")


async def ensure_public_slug(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    *,
    display_name: str | None,
) -> str:
    existing = await db.fetchval(
        """
        SELECT public_slug FROM public.candidates
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        candidate_id,
    )
    if existing:
        return str(existing)
    for _ in range(8):
        slug = f"{_slug_base(display_name)}-{secrets.token_hex(3)}"
        try:
            await db.execute(
                """
                UPDATE public.candidates
                SET public_slug = $2, updated_at = NOW()
                WHERE id = $1::uuid AND public_slug IS NULL
                """,
                candidate_id,
                slug,
            )
            row = await db.fetchval(
                "SELECT public_slug FROM public.candidates WHERE id = $1::uuid",
                candidate_id,
            )
            if row:
                return str(row)
        except asyncpg.UniqueViolationError:
            continue
    fallback = f"candidate-{secrets.token_hex(4)}"
    await db.execute(
        "UPDATE public.candidates SET public_slug = $2 WHERE id = $1::uuid",
        candidate_id,
        fallback,
    )
    return fallback


async def fetch_public_profile(db: asyncpg.Connection, slug: str) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, c.market, c.display_currency,
               c.public_profile_enabled, c.hide_contact_public,
               c.linkedin_url, c.career_profile, c.linkedin_data,
               u.full_name, u.email, u.phone
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.public_slug = $1
          AND c.public_profile_enabled = TRUE
          AND c.deleted_at IS NULL
        """,
        slug.strip(),
    )
    if not row:
        return None

    cand = dict(row)
    display_name = pick_display_name(
        user_full_name=cand.get("full_name"),
        email=cand.get("email"),
    )
    hide_contact = bool(cand.get("hide_contact_public"))

    path_resumes = await db.fetch(
        """
        SELECT id, path_title, status, updated_at
        FROM public.career_path_resumes
        WHERE candidate_id = $1::uuid AND status = 'ready'
        ORDER BY updated_at DESC
        """,
        cand["id"],
    )

    experience = build_merged_experience(
        resume_experience=[],
        linkedin_data=cand.get("linkedin_data"),
        career_profile=cand.get("career_profile")
        if isinstance(cand.get("career_profile"), dict)
        else None,
        career_intelligence=None,
        candidate=cand,
        skills=list(cand.get("skills") or []),
    )

    education = build_merged_education(
        resume_education=[],
        linkedin_data=cand.get("linkedin_data"),
        career_profile=cand.get("career_profile")
        if isinstance(cand.get("career_profile"), dict)
        else None,
    )

    currency = currency_fields_for_candidate(cand)

    return {
        "slug": slug,
        "display_name": display_name,
        "headline": cand.get("headline"),
        "summary": cand.get("summary"),
        "current_title": cand.get("current_title"),
        "current_company": cand.get("current_company"),
        "years_experience": cand.get("years_experience"),
        "location_city": cand.get("location_city"),
        "location_state": cand.get("location_state"),
        "skills": list(cand.get("skills") or []),
        "looking_for": cand.get("looking_for"),
        "linkedin_url": cand.get("linkedin_url"),
        "experience": experience[:8],
        "education": education[:6],
        "career_path_resumes": [
            {
                "id": str(r["id"]),
                "path_title": r["path_title"],
                "download_path": f"/api/v1/career/path-resumes/{r['id']}/download",
            }
            for r in path_resumes
        ],
        "contact": {
            "email": None if hide_contact else cand.get("email"),
            "phone": None if hide_contact else cand.get("phone"),
            "hidden": hide_contact,
        },
        **currency,
    }
