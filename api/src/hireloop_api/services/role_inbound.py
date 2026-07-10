"""
Inbound applicants and external candidate triage for recruiter roles.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from hireloop_api.services.recruiter_search import _role_skills, ensure_role_scoring_job
from hireloop_api.services.resume_parser import ResumeParserService
from hireloop_api.services.skills import canonical_skill


async def score_inbound_profile(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    recruiter_id: uuid.UUID,
    parsed: dict[str, Any],
) -> tuple[float | None, dict[str, Any], list[str], list[str]]:
    """Score parsed resume profile against role brief via skill overlap."""
    _ = recruiter_id
    await ensure_role_scoring_job(db, role_id=role_id, recruiter_id=recruiter_id)

    role = await db.fetchrow(
        """
        SELECT must_haves, nice_to_haves, jd_structured
        FROM public.roles WHERE id = $1 AND deleted_at IS NULL
        """,
        role_id,
    )
    if not role:
        return None, {}, [], []

    job_skills = _role_skills(role)
    skills = parsed.get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    cand_canon = {canonical_skill(str(s)) for s in skills if s}
    matched = [s for s in job_skills if canonical_skill(s) in cand_canon]
    gap = [s for s in job_skills if canonical_skill(s) not in cand_canon]

    if job_skills:
        score = round(len(matched) / len(job_skills), 3)
    else:
        score = 0.5

    criterion_scores = {"skills": score}
    return score, criterion_scores, matched, gap


async def create_inbound_applicant(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    full_name: str,
    email: str | None = None,
    linkedin_url: str | None = None,
    resume_path: str | None = None,
    parsed_profile: dict[str, Any] | None = None,
    source: str = "public_apply",
    recruiter_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Insert inbound applicant and score against role brief."""
    role = await db.fetchrow(
        """
        SELECT id, recruiter_id, title FROM public.roles
        WHERE id = $1 AND deleted_at IS NULL
        """,
        role_id,
    )
    if not role:
        raise ValueError("role_not_found")

    rid = recruiter_id or role["recruiter_id"]
    parsed = parsed_profile or {}
    score, criterion_scores, matched, gap = await score_inbound_profile(
        db,
        role_id=role_id,
        recruiter_id=rid,
        parsed=parsed,
    )

    row = await db.fetchrow(
        """
        INSERT INTO public.role_inbound_applicants
          (role_id, source, full_name, email, linkedin_url, resume_path,
           parsed_profile, match_score, criterion_scores, skills_matched, skills_gap, stage)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9::jsonb, $10, $11, 'search')
        RETURNING id, role_id, full_name, email, match_score, stage, created_at
        """,
        role_id,
        source,
        full_name.strip(),
        (email or "").strip() or None,
        (linkedin_url or "").strip() or None,
        resume_path,
        json.dumps(parsed),
        score,
        json.dumps(criterion_scores),
        matched,
        gap,
    )
    if not row and email:
        row = await db.fetchrow(
            """
            SELECT id, role_id, full_name, email, match_score, stage, created_at
            FROM public.role_inbound_applicants
            WHERE role_id = $1 AND lower(email) = lower($2)
            """,
            role_id,
            email.strip(),
        )
        if row:
            raise ValueError("duplicate_apply")

    return {
        "applicant_id": str(row["id"]),
        "role_id": str(row["role_id"]),
        "full_name": row["full_name"],
        "match_score": row["match_score"],
        "stage": row["stage"],
        "message": "Application received. We'll review your profile against this role.",
    }


def parse_resume_bytes(
    file_bytes: bytes,
    *,
    filename: str,
    mime_type: str | None,
) -> dict[str, Any]:
    """Quick-parse resume into profile dict for inbound scoring."""
    text = ResumeParserService._extract_text(file_bytes, filename, mime_type)
    parsed = ResumeParserService.parse_from_text(text)
    data = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
    skills = data.get("skills") or []
    if isinstance(skills, list):
        skill_names = []
        for s in skills:
            if isinstance(s, dict):
                skill_names.append(s.get("name") or s.get("skill") or "")
            else:
                skill_names.append(str(s))
        data["skills"] = [s for s in skill_names if s]
    return data


async def add_external_candidate(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    recruiter_id: uuid.UUID,
    full_name: str,
    email: str | None = None,
    linkedin_url: str | None = None,
    resume_bytes: bytes | None = None,
    filename: str = "resume.pdf",
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Recruiter adds external profile — same triage pipeline as inbound apply."""
    parsed: dict[str, Any] = {}
    resume_path = None
    if resume_bytes:
        parsed = parse_resume_bytes(resume_bytes, filename=filename, mime_type=mime_type)
        if not full_name and parsed.get("full_name"):
            full_name = str(parsed["full_name"])
        if not email and parsed.get("email"):
            email = str(parsed.get("email"))

    source = "linkedin_url" if linkedin_url and not resume_bytes else "recruiter_add"
    return await create_inbound_applicant(
        db,
        role_id=role_id,
        full_name=full_name or "External candidate",
        email=email,
        linkedin_url=linkedin_url,
        resume_path=resume_path,
        parsed_profile=parsed,
        source=source,
        recruiter_id=recruiter_id,
    )
