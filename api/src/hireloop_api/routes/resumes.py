"""
Resume upload and parsing routes.

POST /api/v1/resumes/upload
  - Accepts multipart/form-data with a PDF or DOCX file
  - Uploads to Supabase Storage (bucket: resumes)
  - Queues durable multi-tier parsing (async)
  - Returns storage path + parsed data

GET  /api/v1/resumes/{resume_id}
  - Returns parsed resume data for a specific resume

POST /api/v1/resumes/{resume_id}/apply-to-profile
  - Copies parsed data into the candidate's profile row
"""

import asyncio
import json
import re
import uuid
from typing import Annotated, Any, Literal

import asyncpg
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from supabase import Client, create_client

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_db_pool, get_phone_verified_user
from hireloop_api.services.candidate_display_name import sync_preferred_name_from_resume
from hireloop_api.services.file_security import (
    ALLOWED_RESUME_MIME_TYPES,
    MAX_RESUME_BYTES,
    resume_magic_ok,
    validate_resume_upload,
)
from hireloop_api.services.rate_limit import check_rate_limit
from hireloop_api.services.resume_parser import ParsedResume, ResumeParserService

logger = structlog.get_logger()

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _normalize_resume_mime(content_type: str | None, file_bytes: bytes) -> str:
    """Browsers (especially mobile) often send application/octet-stream for PDFs."""
    if content_type in ALLOWED_RESUME_MIME_TYPES and content_type != "application/octet-stream":
        return content_type or "application/pdf"
    if resume_magic_ok(file_bytes):
        if file_bytes[:4] == b"%PDF":
            return "application/pdf"
        if file_bytes[:4] == b"PK\x03\x04":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "application/msword"
    return content_type or "application/octet-stream"


def _quick_parse_resume(
    file_bytes: bytes,
    *,
    filename: str,
    mime_type: str | None,
) -> ParsedResume:
    """Fast regex-only parse — returns in milliseconds so onboarding never blocks."""
    text = ResumeParserService._extract_text(file_bytes, filename, mime_type)
    return ResumeParserService.parse_from_text(text)


class ResumeUploadResponse(BaseModel):
    resume_id: str
    file_path: str
    parsed: ParsedResume
    message: str
    parse_status: Literal["pending", "ready", "failed"] = "ready"


class ResumeStatusResponse(BaseModel):
    resume_id: str
    parse_status: Literal["pending", "ready", "failed"]
    parsed: ParsedResume | None = None
    message: str | None = None


class ApplyToProfileResponse(BaseModel):
    message: str
    fields_updated: list[str]
    starter_jobs: list[dict] = []


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
        INSERT INTO public.candidates (
          user_id, headline, profile_complete,
          hide_contact_public, share_with_recruiters, public_profile_enabled
        )
        VALUES ($1::uuid, $2, FALSE, TRUE, FALSE, FALSE)
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

    try:
        from hireloop_api.services.public_profile import bootstrap_candidate_public_profile

        user_row = await db.fetchrow(
            "SELECT full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
            user_uuid,
        )
        await bootstrap_candidate_public_profile(
            db,
            candidate["id"],
            user_id=user_uuid,
            display_name=user_row.get("full_name") if user_row else None,
        )
    except Exception as exc:
        logger.error(
            "candidate_sharing_bootstrap_failed",
            user_id=str(user_uuid),
            error=str(exc),
        )

    return candidate


_parse_tasks: set[asyncio.Task[None]] = set()


def _parse_status_from_row(
    parsed_data: Any,
) -> tuple[Literal["pending", "ready", "failed"], str | None]:
    if isinstance(parsed_data, str):
        try:
            parsed_data = json.loads(parsed_data)
        except json.JSONDecodeError:
            return "ready", None
    if not isinstance(parsed_data, dict):
        return "ready", None
    marker = parsed_data.get("_parse_status")
    if marker == "pending":
        return "pending", None
    if marker == "failed":
        return "failed", parsed_data.get("_parse_error") or "Couldn't parse that CV."
    return "ready", None


def _parsed_resume_from_row(parsed_data: Any) -> ParsedResume | None:
    status, _ = _parse_status_from_row(parsed_data)
    if status != "ready":
        return None
    if isinstance(parsed_data, str):
        payload = json.loads(parsed_data)
    else:
        payload = dict(parsed_data)
    payload.pop("_parse_status", None)
    payload.pop("_parse_error", None)
    return ParsedResume.model_validate(payload)


def _schedule_resume_parse(
    *,
    user_id: str,
    candidate_id: str,
    resume_id: str,
    file_bytes: bytes,
    filename: str,
    mime_type: str | None,
    settings: Settings,
) -> asyncio.Task[None]:
    """Run LLM parsing off the upload request so proxies don't time out."""

    async def _run() -> None:
        try:
            import hashlib

            from hireloop_api.services.resume_parser import PARSER_VERSION

            content_hash = hashlib.sha256(file_bytes).hexdigest()
            pool = await get_db_pool(settings)

            # Same file + same parser version → same result. Serve from cache
            # instead of re-running the LLM chain (re-uploads are very common).
            parsed: ParsedResume | None = None
            async with pool.acquire() as cache_db:
                cached = await cache_db.fetchval(
                    "SELECT parsed FROM public.resume_parse_cache "
                    "WHERE content_hash = $1 AND parser_version = $2",
                    content_hash,
                    PARSER_VERSION,
                )
            if cached:
                try:
                    payload = json.loads(cached) if isinstance(cached, str) else cached
                    parsed = ParsedResume.model_validate(payload)
                    logger.info("resume_parse_cache_hit", resume_id=resume_id)
                except Exception:
                    parsed = None

            if parsed is None:
                parsed = await ResumeParserService.parse_best(
                    file_bytes=file_bytes,
                    filename=filename,
                    mime_type=mime_type,
                    settings=settings,
                )
                # Only cache parses worth reusing (identity present).
                if parsed.full_name or parsed.current_title:
                    async with pool.acquire() as cache_db:
                        await cache_db.execute(
                            "INSERT INTO public.resume_parse_cache "
                            "  (content_hash, parser_version, parsed) "
                            "VALUES ($1, $2, $3::jsonb) "
                            "ON CONFLICT (content_hash, parser_version) DO NOTHING",
                            content_hash,
                            PARSER_VERSION,
                            parsed.model_dump_json(),
                        )

            async with pool.acquire() as bg_db:
                await bg_db.execute(
                    """
                    UPDATE public.resumes
                    SET parsed_data = $2::jsonb,
                        raw_text = $3
                    WHERE id = $1::uuid
                    """,
                    uuid.UUID(resume_id),
                    parsed.model_dump_json(),
                    parsed.raw_text,
                )
                await _sync_user_display_name_from_resume(
                    bg_db,
                    user_id=user_id,
                    candidate_id=candidate_id,
                    resume_full_name=parsed.full_name,
                )
                # The schema retains market fields for compatibility. The market
                # resolver is India-only and ignores non-India locations.
                if parsed.location_city or parsed.location_state:
                    from hireloop_api.market_db import sync_candidate_market_from_location

                    try:
                        await sync_candidate_market_from_location(
                            bg_db,
                            candidate_id=uuid.UUID(candidate_id),
                            location_city=parsed.location_city,
                            location_state=parsed.location_state,
                        )
                    except Exception as exc:
                        logger.warning("bg_market_sync_failed", error=str(exc)[:150])
                try:
                    await bg_db.execute(
                        """
                        INSERT INTO public.consent_log (user_id, purpose, granted)
                        VALUES ($1::uuid, 'resume_upload', TRUE)
                        """,
                        uuid.UUID(user_id),
                    )
                except Exception as exc:
                    logger.error(
                        "consent_log_insert_failed",
                        user_id=user_id,
                        error=str(exc),
                    )
        except Exception as exc:
            logger.error(
                "resume_background_parse_failed",
                resume_id=resume_id,
                candidate_id=candidate_id,
                error=str(exc)[:300],
            )
            try:
                pool = await get_db_pool(settings)
                async with pool.acquire() as bg_db:
                    await bg_db.execute(
                        """
                        UPDATE public.resumes
                        SET parsed_data = $2::jsonb
                        WHERE id = $1::uuid
                        """,
                        uuid.UUID(resume_id),
                        json.dumps(
                            {
                                "_parse_status": "failed",
                                "_parse_error": "Couldn't parse that CV. Try another file.",
                            }
                        ),
                    )
            except Exception as mark_exc:
                logger.error(
                    "resume_parse_failed_marker_write",
                    resume_id=resume_id,
                    error=str(mark_exc)[:200],
                )
            # Let the durable queue apply bounded backoff/retries. The failed
            # marker keeps the UI honest if all attempts are exhausted.
            raise

    task = asyncio.create_task(_run())
    _parse_tasks.add(task)
    task.add_done_callback(_parse_tasks.discard)
    return task


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
    *,
    overwrite: bool = False,
) -> tuple[dict[str, object], list[str]]:
    """Diff parsed resume data against the profile.

    fill (default): only populate fields that are currently empty.
    overwrite: parsed non-null values win — used when the candidate
    deliberately replaces their CV and expects the profile to follow it.
    """
    updates: dict[str, object] = {}
    fields_updated: list[str] = []

    def _normalize_location_city(raw: str | None, full_name: str | None) -> str | None:
        if not raw:
            return None
        v = str(raw).strip()
        if not v:
            return None
        # Guard against resume parsers accidentally prepending the candidate's name.
        # Example: "nayak Bengaluru" where "Nayak" is a name token, not a city.
        if full_name:
            name_tokens = {
                t.lower() for t in re.split(r"[\s,./|-]+", str(full_name)) if t and len(t) > 1
            }
            parts = [p for p in re.split(r"\s+", v) if p]
            while parts and parts[0].lower() in name_tokens:
                parts.pop(0)
            v = " ".join(parts).strip()
        if not v:
            return None
        # Alias metro variants so matches don't score as 0.2 "far city"
        # (Bangalore Urban vs Bengaluru was wiping Ops Manager matches).
        aliases = {
            "bangalore": "Bengaluru",
            "bangalore urban": "Bengaluru",
            "bengalooru": "Bengaluru",
            "gurgaon": "Gurugram",
            "bombay": "Mumbai",
            "madras": "Chennai",
            "calcutta": "Kolkata",
            "new delhi": "Delhi",
        }
        return aliases.get(v.lower(), v)

    def _normalize_skills(raw_skills: list[str] | None) -> list[str]:
        from hireloop_api.services.skills import display_skill

        cleaned: list[str] = []
        seen = set()
        for s in raw_skills or []:
            t = str(s).strip()
            if not t:
                continue
            low = t.lower()
            # Drop obvious junk.
            if "http://" in low or "https://" in low or "www." in low:
                continue
            if "/" in t and "." in t:
                # Usually a URL/domain fragment.
                continue
            if len(t) > 60:
                continue
            # Prefer canonical display labels for known skills; otherwise title-case.
            label = display_skill(t)
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(label)
        return cleaned

    def maybe_update(field: str, value: object) -> None:
        if not value:
            return
        if overwrite:
            if candidate[field] != value:
                updates[field] = value
                fields_updated.append(field)
        elif not candidate[field]:
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
    maybe_update("location_city", _normalize_location_city(parsed.location_city, parsed.full_name))
    maybe_update("location_state", parsed.location_state)

    if parsed.skills:
        existing_skills = set(candidate["skills"] or [])
        normalized_skills = _normalize_skills(parsed.skills)
        if overwrite:
            # The new CV's skill set is the source of truth on replace.
            new_skills = set(normalized_skills)
        else:
            new_skills = existing_skills | set(normalized_skills)
        if new_skills != existing_skills:
            updates["skills"] = list(new_skills)
            fields_updated.append("skills")

    if parsed.career_profile:
        updates["career_profile"] = parsed.career_profile
        fields_updated.append("career_profile")
    if parsed.career_analysis:
        updates["career_analysis"] = parsed.career_analysis
        fields_updated.append("career_analysis")

    if overwrite:
        # Any deliberate CV upload counts as profile activation — even sparse parses.
        updates["profile_complete"] = True
        if "profile_complete" not in fields_updated:
            fields_updated.append("profile_complete")
    else:
        profile_will_have_title = bool(updates.get("current_title") or candidate["current_title"])
        profile_will_have_experience = bool(
            updates.get("years_experience") or candidate["years_experience"]
        )
        profile_will_have_skills = bool(updates.get("skills") or candidate["skills"])
        if profile_will_have_title and (profile_will_have_experience or profile_will_have_skills):
            updates["profile_complete"] = True
            fields_updated.append("profile_complete")

    return updates, fields_updated


async def _sync_user_display_name_from_resume(
    db: asyncpg.Connection,
    *,
    user_id: str,
    candidate_id: str,
    resume_full_name: str | None,
) -> None:
    """Persist résumé name on users + Aarya career_facts when appropriate."""
    await sync_preferred_name_from_resume(
        db,
        user_id=user_id,
        candidate_id=candidate_id,
        resume_full_name=resume_full_name,
    )


@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    file: Annotated[UploadFile, File(description="PDF or DOCX resume, max 10MB")],
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> ResumeUploadResponse:
    """
    Upload a resume, queue durable parsing, and store the result.
    The candidate can then choose to apply parsed data to their profile.
    """
    # Parsing is a multi-tier LLM job — cap per user per hour (cost guard).
    check_rate_limit(str(current_user["id"]), "resume_upload", max_per_hour=15)

    # Read at most one byte over the limit so oversized requests do not become
    # unbounded per-request memory allocations.
    file_bytes = await file.read(MAX_RESUME_BYTES + 1)
    validation_error = validate_resume_upload(file.content_type, file_bytes)
    if validation_error and len(file_bytes) > MAX_RESUME_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10MB.",
        )
    if validation_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation_error,
        )

    normalized_mime = _normalize_resume_mime(file.content_type, file_bytes)
    filename = file.filename or "resume.pdf"
    quick_parsed = _quick_parse_resume(
        file_bytes,
        filename=filename,
        mime_type=normalized_mime,
    )

    user_id = current_user["id"]

    candidate = await _ensure_candidate_for_resume_upload(
        db,
        user_id=user_id,
        headline="New candidate",
    )

    candidate_id = str(candidate["id"])
    resume_id = str(uuid.uuid4())
    file_ext = "pdf" if "pdf" in normalized_mime else "docx"
    storage_path = f"{user_id}/{resume_id}.{file_ext}"

    supabase: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    try:
        await asyncio.to_thread(
            supabase.storage.from_("resumes").upload,
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": normalized_mime},
        )
    except Exception as exc:
        logger.error(
            "resume_storage_upload_failed",
            candidate_id=candidate_id,
            path=storage_path,
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Couldn't store your CV. Check that Supabase Storage bucket "
                "'resumes' exists and SUPABASE_SERVICE_KEY is set on the API."
            ),
        ) from exc

    logger.info("resume_uploaded", candidate_id=candidate_id, path=storage_path)

    await _prepare_candidate_resume_storage(
        db,
        candidate_id=candidate_id,
        storage_path=storage_path,
    )

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
        filename,
        len(file_bytes),
        normalized_mime,
        quick_parsed.model_dump_json(),
        quick_parsed.raw_text,
    )

    await _sync_user_display_name_from_resume(
        db,
        user_id=user_id,
        candidate_id=candidate_id,
        resume_full_name=quick_parsed.full_name,
    )

    from hireloop_api.services.background_jobs import RESUME_PARSE, enqueue_job

    await enqueue_job(
        db,
        kind=RESUME_PARSE,
        payload={
            "user_id": str(user_id),
            "candidate_id": candidate_id,
            "resume_id": resume_id,
            "storage_path": storage_path,
            "filename": filename,
            "mime_type": normalized_mime,
        },
        idempotency_key=f"resume_parse:{resume_id}",
        max_attempts=4,
    )

    was_parsed = bool(quick_parsed.skills or quick_parsed.current_title or quick_parsed.full_name)
    return ResumeUploadResponse(
        resume_id=resume_id,
        file_path=storage_path,
        parsed=quick_parsed,
        parse_status="ready",
        message=(
            "Resume uploaded and parsed. Review the data and apply to your profile."
            if was_parsed
            else (
                "Resume uploaded. Aarya is enriching your profile in the background — "
                "you can continue and refine details from the dashboard."
            )
        ),
    )


@router.get("/{resume_id}", response_model=ResumeStatusResponse)
async def get_resume_status(
    resume_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> ResumeStatusResponse:
    """Poll parse progress after upload — onboarding waits here for parsed fields."""
    resume = await db.fetchrow(
        """
        SELECT r.id, r.parsed_data
        FROM public.resumes r
        JOIN public.candidates c ON c.id = r.candidate_id
        WHERE r.id = $1::uuid AND c.user_id = $2::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(resume_id),
        uuid.UUID(str(current_user["id"])),
    )
    if not resume:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found or access denied.",
        )

    parse_status, failure_message = _parse_status_from_row(resume["parsed_data"])
    parsed = _parsed_resume_from_row(resume["parsed_data"])
    return ResumeStatusResponse(
        resume_id=str(resume["id"]),
        parse_status=parse_status,
        parsed=parsed,
        message=failure_message,
    )


@router.post("/{resume_id}/apply-to-profile", response_model=ApplyToProfileResponse)
async def apply_to_profile(
    resume_id: str,
    mode: str = Query(default="fill", pattern="^(fill|replace)$"),
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> ApplyToProfileResponse:
    """
    Copy parsed resume data into the candidate's profile.

    mode=fill (default): only fills fields that are currently empty.
    mode=replace: parsed non-null values overwrite the profile — used when the
    candidate deliberately replaces their CV and expects the overview to update.
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

    parsed = _parsed_resume_from_row(resume["parsed_data"])
    if parsed is None:
        parse_status, message = _parse_status_from_row(resume["parsed_data"])
        if parse_status == "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Resume is still being parsed. Try again in a moment.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message or "Resume could not be parsed.",
        )
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

    updates, fields_updated = _build_profile_updates_from_resume(
        dict(candidate), parsed, overwrite=(mode == "replace")
    )

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
            "UPDATE public.candidates SET "
            f"{', '.join(set_clauses)}, updated_at = NOW() WHERE id = $1"
        )
        await db.execute(
            update_query,
            uuid.UUID(candidate_id),
            *values,
        )

    loc_city = updates.get("location_city") or candidate["location_city"]
    loc_state = updates.get("location_state") or candidate["location_state"]
    if loc_city or loc_state:
        from hireloop_api.market_db import sync_candidate_market_from_location

        await sync_candidate_market_from_location(
            db,
            candidate_id=uuid.UUID(candidate_id),
            location_city=str(loc_city) if loc_city else None,
            location_state=str(loc_state) if loc_state else None,
        )

    await _sync_user_display_name_from_resume(
        db,
        user_id=user_id,
        candidate_id=candidate_id,
        resume_full_name=parsed.full_name,
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
        AARYA_AUTO_INGEST,
        CAREER_INTELLIGENCE_UPDATE,
        CAREER_PATH_UPDATE,
        MATCH_EMBED_CANDIDATE,
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
        kind=MATCH_EMBED_CANDIDATE,
        payload={"candidate_id": candidate_id},
        idempotency_key=f"match_embed_apply:{candidate_id}",
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
    await enqueue_job(
        db,
        kind=AARYA_AUTO_INGEST,
        payload={"candidate_id": candidate_id, "force_refresh": True},
        idempotency_key=f"aarya_auto_ingest:{candidate_id}",
    )

    starter_jobs: list[dict] = []
    try:
        from hireloop_api.services.instant_shelf import fetch_instant_shelf

        starter_jobs = await fetch_instant_shelf(
            db,
            user_id=user_id,
            settings=settings,
            limit=10,
        )
    except Exception as exc:
        logger.warning(
            "apply_profile_instant_shelf_failed",
            candidate_id=candidate_id,
            error=str(exc)[:200],
        )

    return ApplyToProfileResponse(
        message=f"Profile updated with {len(fields_updated)} fields from your resume.",
        fields_updated=fields_updated,
        starter_jobs=starter_jobs,
    )
