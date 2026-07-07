"""
Full candidate profile for tailored resume generation.

Merges resume parse, LinkedIn, career_profile, and candidate fields so the LLM
has complete work history and education — without inventing beyond this payload.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from hireloop_api.services.profile_experience import (
    build_merged_education,
    build_merged_experience,
)


async def load_tailored_resume_profile(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Rich source-of-truth dict for resume tailoring prompts."""
    row = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, c.linkedin_url, c.linkedin_data, c.career_profile,
               c.expected_ctc_min, c.expected_ctc_max, c.notice_period_days,
               u.full_name, u.email, u.phone
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    if not row:
        return None

    data = dict(row)
    data["skills"] = list(data.get("skills") or [])

    resume_experience: list[dict[str, Any]] = []
    resume_education: list[dict[str, Any]] = []
    resume_row = await db.fetchrow(
        """
        SELECT parsed_data, file_name
        FROM public.resumes
        WHERE candidate_id = $1::uuid
        ORDER BY is_primary DESC, version DESC, created_at DESC
        LIMIT 1
        """,
        candidate_id,
    )
    parsed = resume_row["parsed_data"] if resume_row else None
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (ValueError, TypeError):
            parsed = None
    if isinstance(parsed, dict):
        raw_name = parsed.get("full_name")
        if isinstance(raw_name, str) and raw_name.strip():
            data["resume_full_name"] = raw_name.strip()
        raw_exp = parsed.get("work_experience")
        if isinstance(raw_exp, list):
            resume_experience = [e for e in raw_exp if isinstance(e, dict)]
        raw_edu = parsed.get("education")
        if isinstance(raw_edu, list):
            resume_education = [e for e in raw_edu if isinstance(e, dict)]
        if parsed.get("summary") and not data.get("summary"):
            data["summary"] = parsed.get("summary")
        raw_skills = parsed.get("skills")
        if isinstance(raw_skills, list):
            for skill in raw_skills:
                s = str(skill).strip()
                if s and s not in data["skills"]:
                    data["skills"].append(s)

    career_profile = data.get("career_profile")
    if isinstance(career_profile, str):
        try:
            career_profile = json.loads(career_profile)
        except (ValueError, TypeError):
            career_profile = None
    if not isinstance(career_profile, dict):
        career_profile = None

    career_intel = None
    try:
        from hireloop_api.services.career_intelligence import CareerIntelligenceService

        career_intel = await CareerIntelligenceService.get(db, str(candidate_id))
    except Exception:
        career_intel = None

    candidate_stub = {
        "current_title": data.get("current_title"),
        "current_company": data.get("current_company"),
        "headline": data.get("headline"),
        "summary": data.get("summary"),
    }
    experience = build_merged_experience(
        resume_experience=resume_experience,
        linkedin_data=data.get("linkedin_data"),
        career_profile=career_profile,
        career_intelligence=career_intel,
        candidate=candidate_stub,
        skills=data["skills"],
    )
    education = build_merged_education(
        resume_education=resume_education,
        linkedin_data=data.get("linkedin_data"),
        career_profile=career_profile,
    )

    return {
        "full_name": data.get("resume_full_name") or data.get("full_name"),
        "email": data.get("email"),
        "phone": data.get("phone"),
        "headline": data.get("headline"),
        "summary": data.get("summary"),
        "current_title": data.get("current_title"),
        "current_company": data.get("current_company"),
        "years_experience": data.get("years_experience"),
        "location_city": data.get("location_city"),
        "location_state": data.get("location_state"),
        "looking_for": data.get("looking_for"),
        "linkedin_url": data.get("linkedin_url"),
        "skills": data["skills"],
        "expected_ctc_min": data.get("expected_ctc_min"),
        "expected_ctc_max": data.get("expected_ctc_max"),
        "notice_period_days": data.get("notice_period_days"),
        "experience": experience[:12],
        "education": education[:8],
        "source_note": (
            "All employers, titles, dates, education, and metrics MUST match this "
            "profile exactly. Rephrase bullets for the job; never invent or alter facts."
        ),
    }
