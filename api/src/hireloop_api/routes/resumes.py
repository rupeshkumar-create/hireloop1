"""
Resume upload and parsing routes.

POST /api/v1/resumes/upload
  - Accepts multipart/form-data with a PDF or DOCX file
  - Uploads to Supabase Storage (bucket: resumes)
  - Triggers Affinda parsing (async)
  - Returns storage path + parsed data

GET  /api/v1/resumes/{resume_id}
  - Returns parsed resume data for a specific resume

POST /api/v1/resumes/{resume_id}/apply-to-profile
  - Copies parsed data into the candidate's profile row
"""

import json
import uuid
from typing import Annotated

import asyncpg
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from supabase import Client, create_client

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_india_verified_user
from hireloop_api.services.rate_limit import check_rate_limit
from hireloop_api.services.resume_parser import ParsedResume, ResumeParserService

logger = structlog.get_logger()

router = APIRouter(prefix="/resumes", tags=["resumes"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


class ResumeUploadResponse(BaseModel):
    resume_id: str
    file_path: str
    parsed: ParsedResume
    message: str


class ApplyToProfileResponse(BaseModel):
    message: str
    fields_updated: list[str]


async def _ensure_candidate_for_resume_upload(
    db: asyncpg.Connection,
    *,
    user_id: str,
    headline: str,
) -> asyncpg.Record:
    """
    Resume upload is part of onboarding, so it must recover if OAuth bootstrap
    did not create the candidate row yet.
    """
    user_uuid = uuid.UUID(user_id)
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        user_uuid,
    )
    if candidate:
        return candidate

    await db.execute(
        """
        INSERT INTO public.candidates (user_id, headline, profile_complete)
        VALUES ($1::uuid, $2, FALSE)
        """,
        user_uuid,
        headline,
    )
    try:
        await db.execute(
            """
            INSERT INTO public.consent_log (user_id, purpose, granted)
            VALUES ($1::uuid, 'profile_creation', TRUE)
            """,
            user_uuid,
        )
    except Exception as exc:
        logger.error("consent_log_insert_failed", user_id=str(user_uuid), error=str(exc))

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        user_uuid,
    )
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create candidate profile. Please try again.",
        )
    return candidate


async def _prepare_candidate_resume_storage(
    db: asyncpg.Connection,
    *,
    candidate_id: str,
    storage_path: str,
) -> None:
    """Mark the incoming CV as the current one and persist its Supabase path."""
    candidate_uuid = uuid.UUID(candidate_id)
    await db.execute(
        """
        UPDATE public.resumes
        SET is_primary = FALSE
        WHERE candidate_id = $1::uuid
        """,
        candidate_uuid,
    )
    await db.execute(
        """
        UPDATE public.candidates
        SET resume_path = $2,
            updated_at = NOW()
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        candidate_uuid,
        storage_path,
    )


def _build_profile_updates_from_resume(
    candidate: dict,
    parsed: ParsedResume,
) -> tuple[dict[str, object], list[str]]:
    updates: dict[str, object] = {}
    fields_updated: list[str] = []

    def maybe_update(field: str, value: object) -> None:
        if value and not candidate[field]:
            updates[field] = value
            fields_updated.append(field)

    maybe_update("headline", parsed.headline)
    maybe_update("summary", parsed.summary)
    maybe_update("current_title", parsed.current_title)
    maybe_update("current_company", parsed.current_company)
    maybe_update("years_experience", parsed.years_experience)
    maybe_update("expected_ctc_min", parsed.expected_ctc_min)
    maybe_update("expected_ctc_max", parsed.expected_ctc_max)
    maybe_update("current_ctc", parsed.current_ctc)
    maybe_update("notice_period_days", parsed.notice_period_days)
    maybe_update("linkedin_url", parsed.linkedin_url)
    maybe_update("github_url", parsed.github_url)
    maybe_update("location_city", parsed.location_city)
    maybe_update("location_state", parsed.location_state)

    if parsed.skills:
        existing_skills = set(candidate["skills"] or [])
        new_skills = existing_skills | set(parsed.skills)
        if new_skills != existing_skills:
            updates["skills"] = list(new_skills)
            fields_updated.append("skills")

    if parsed.career_profile:
        updates["career_profile"] = parsed.career_profile
        fields_updated.append("career_profile")
    if parsed.career_analysis:
        updates["career_analysis"] = parsed.career_analysis
        fields_updated.append("career_analysis")

    profile_will_have_title = bool(updates.get("current_title") or candidate["current_title"])
    profile_will_have_experience = bool(
        updates.get("years_experience") or candidate["years_experience"]
    )
    profile_will_have_skills = bool(updates.get("skills") or candidate["skills"])
    if profile_will_have_title and (profile_will_have_experience or profile_will_have_skills):
        updates["profile_complete"] = True
        fields_updated.append("profile_complete")

    return updates, fields_updated


@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    file: Annotated[UploadFile, File(description="PDF or DOCX resume, max 10MB")],
    current_user: dict = Depends(get_india_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> ResumeUploadResponse:
    """
    Upload a resume, parse it with Affinda, and store the result.
    The candidate can then choose to apply parsed data to their profile.
    """
    # Parsing is a multi-tier LLM job — cap per user per hour (cost guard).
    check_rate_limit(str(current_user["id"]), "resume_upload", max_per_hour=15)

    # Validate file type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' not supported. Upload PDF or DOCX.",
        )

    # Read file bytes (validate size)
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10MB.",
        )

    # Defense-in-depth: the client-supplied content_type is spoofable, so verify
    # the file's magic bytes actually match an allowed document type (PDF / DOCX
    # zip / legacy DOC OLE) before we store or parse it.
    magic = file_bytes[:4]
    if magic not in (b"%PDF", b"PK\x03\x04", b"\xd0\xcf\x11\xe0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content doesn't look like a PDF or DOCX.",
        )

    user_id = current_user["id"]

    candidate = await _ensure_candidate_for_resume_upload(
        db,
        user_id=user_id,
        headline="New candidate",
    )

    candidate_id = str(candidate["id"])
    resume_id = str(uuid.uuid4())
    file_ext = "pdf" if "pdf" in (file.content_type or "") else "docx"
    storage_path = f"{user_id}/{resume_id}.{file_ext}"

    supabase: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    supabase.storage.from_("resumes").upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": file.content_type or "application/pdf"},
    )

    logger.info("resume_uploaded", candidate_id=candidate_id, path=storage_path)

    # Advanced multi-tier parse: Affinda (if keyed) → LLM/OpenRouter → regex.
    # parse_best() never raises and field-merges the richest result so onboarding
    # always fills profile fields from the CV, even with zero external keys.
    parsed: ParsedResume = await ResumeParserService.parse_best(
        file_bytes=file_bytes,
        filename=file.filename or f"resume.{file_ext}",
        mime_type=file.content_type,
        settings=settings,
    )

    await _prepare_candidate_resume_storage(
        db,
        candidate_id=candidate_id,
        storage_path=storage_path,
    )

    # Store resume record in DB. Previous resumes were demoted above, so this
    # row is the current CV used by profile display and matching.
    await db.execute(
        """
        INSERT INTO public.resumes
          (id, candidate_id, file_path, file_name, file_size_bytes, mime_type,
           parsed_data, raw_text, version, is_primary)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, 1, TRUE)
        ON CONFLICT DO NOTHING
        """,
        uuid.UUID(resume_id),
        uuid.UUID(candidate_id),
        storage_path,
        file.filename or f"resume.{file_ext}",
        len(file_bytes),
        file.content_type,
        parsed.model_dump_json(),
        parsed.raw_text,
    )

    logger.info("resume_parsed", candidate_id=candidate_id, skills_count=len(parsed.skills))

    # DPDP audit: record consent for resume upload/parsing (non-fatal if it fails)
    try:
        await db.execute(
            """
            INSERT INTO public.consent_log (user_id, purpose, granted)
            VALUES ($1, 'resume_upload', TRUE)
            """,
            uuid.UUID(user_id),
        )
    except Exception as exc:
        logger.error("consent_log_insert_failed", user_id=str(user_id), error=str(exc))

    was_parsed = bool(parsed.skills or parsed.current_title or parsed.full_name)
    return ResumeUploadResponse(
        resume_id=resume_id,
        file_path=storage_path,
        parsed=parsed,
        message=(
            "Resume uploaded and parsed. Review the data and apply to your profile."
            if was_parsed
            else (
                "Resume uploaded. Auto-parsing is not configured - "
                "you can fill your profile manually."
            )
        ),
    )


@router.post("/{resume_id}/apply-to-profile", response_model=ApplyToProfileResponse)
async def apply_to_profile(
    resume_id: str,
    current_user: dict = Depends(get_india_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> ApplyToProfileResponse:
    """
    Copy parsed resume data into the candidate's profile.
    Only fills fields that are currently empty (never overwrites existing data).
    """
    user_id = current_user["id"]

    # Fetch resume + verify ownership
    resume = await db.fetchrow(
        """
        SELECT r.parsed_data, r.candidate_id
        FROM public.resumes r
        JOIN public.candidates c ON c.id = r.candidate_id
        WHERE r.id = $1 AND c.user_id = $2
        """,
        uuid.UUID(resume_id),
        uuid.UUID(user_id),
    )

    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found or access denied.",
        )

    parsed = ParsedResume.model_validate(json.loads(resume["parsed_data"]))
    candidate_id = str(resume["candidate_id"])

    # Build update dict — only set fields that are non-null in parsed and empty in profile
    candidate = await db.fetchrow(
        """
        SELECT headline, summary, current_title, current_company,
               years_experience, expected_ctc_min, expected_ctc_max, current_ctc,
               notice_period_days, skills, linkedin_url, github_url,
               location_city, location_state, career_profile, career_analysis
        FROM public.candidates WHERE id = $1
        """,
        uuid.UUID(candidate_id),
    )

    updates, fields_updated = _build_profile_updates_from_resume(dict(candidate), parsed)

    if updates:
        set_clauses: list[str] = []
        values: list[object] = []
        for idx, (key, value) in enumerate(updates.items(), start=2):
            if key in {"career_profile", "career_analysis"}:
                set_clauses.append(f"{key} = ${idx}::jsonb")
                values.append(json.dumps(value))
            else:
                set_clauses.append(f"{key} = ${idx}")
                values.append(value)
        # Field names come only from the fixed update builder above.
        update_query = (
            "UPDATE public.candidates SET "  # noqa: S608
            f"{', '.join(set_clauses)}, updated_at = NOW() WHERE id = $1"
        )
        await db.execute(
            update_query,
            uuid.UUID(candidate_id),
            *values,
        )

    logger.info(
        "profile_updated_from_resume",
        candidate_id=candidate_id,
        fields=fields_updated,
    )

    # DPDP audit: record consent for applying resume fields to profile (non-fatal)
    try:
        await db.execute(
            """
            INSERT INTO public.consent_log (user_id, purpose, granted)
            VALUES ($1, 'resume_apply_to_profile', TRUE)
            """,
            uuid.UUID(user_id),
        )
    except Exception as exc:
        logger.error("consent_log_insert_failed", user_id=str(user_id), error=str(exc))

    from hireloop_api.services.background_jobs import (
        CAREER_INTELLIGENCE_UPDATE,
        CAREER_PATH_UPDATE,
        RESUME_EMBED_SCORE,
        enqueue_job,
    )

    await enqueue_job(
        db,
        kind=RESUME_EMBED_SCORE,
        payload={"candidate_id": candidate_id},
        idempotency_key=f"resume_embed_score:{candidate_id}",
    )
    await enqueue_job(
        db,
        kind=CAREER_INTELLIGENCE_UPDATE,
        payload={"candidate_id": candidate_id, "only_if_missing": False},
        idempotency_key=f"career_intel:{candidate_id}",
    )
    await enqueue_job(
        db,
        kind=CAREER_PATH_UPDATE,
        payload={"candidate_id": candidate_id},
        idempotency_key=f"career_path_update:{candidate_id}",
    )

    return ApplyToProfileResponse(
        message=f"Profile updated with {len(fields_updated)} fields from your resume.",
        fields_updated=fields_updated,
    )
