"""Public candidate profiles — no auth required when published."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_current_user_optional, get_db
from hireloop_api.rate_limit import _client_ip
from hireloop_api.services.distributed_rate_limit import check_distributed_rate_limit
from hireloop_api.services.file_security import MAX_RESUME_BYTES, validate_resume_upload
from hireloop_api.services.public_profile import fetch_public_profile
from hireloop_api.services.public_profile_chat import (
    list_public_profile_messages,
    send_public_profile_message,
    stream_public_profile_message,
)
from hireloop_api.services.public_role import fetch_public_role
from hireloop_api.services.role_inbound import create_inbound_applicant, parse_resume_bytes

logger = structlog.get_logger()

router = APIRouter(prefix="/public", tags=["public"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


async def _limit_public_request(
    request: Request,
    db,
    settings: Settings,
    bucket: str,
    max_per_hour: int,
) -> None:
    identity_hash = hmac.new(
        settings.secret_key.encode(),
        _client_ip(request).encode(),
        hashlib.sha256,
    ).hexdigest()
    await check_distributed_rate_limit(
        db,
        identity_hash=identity_hash,
        bucket=bucket,
        max_per_hour=max_per_hour,
    )


class PublicProfileChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    visitor_session_id: uuid.UUID


@router.get("/profiles/{slug}")
async def get_public_profile(
    slug: str,
    role: str | None = None,
    db=Depends(get_db),
    settings: Settings = Depends(get_settings),
    viewer: dict | None = Depends(get_current_user_optional),
) -> dict:
    """World-readable profile when the candidate has published it."""
    profile = await fetch_public_profile(db, slug, viewer=viewer, role_slug=role)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found or not published.")

    try:
        owner = await db.fetchrow(
            """
            SELECT c.user_id::text AS user_id
            FROM public.candidates c
            WHERE c.public_slug = $1 AND c.public_profile_enabled = TRUE AND c.deleted_at IS NULL
            """,
            slug.strip(),
        )
        if owner:
            from hireloop_api.services.notifications import notify_profile_viewed

            await notify_profile_viewed(
                db,
                settings,
                candidate_user_id=owner["user_id"],
                slug=slug.strip(),
            )
    except Exception as exc:
        logger.warning("public_profile_notify_failed", error=str(exc)[:200])

    return profile


@router.get("/profiles/{slug}/chat/messages")
async def get_public_profile_chat(
    slug: str,
    visitor_session_id: uuid.UUID,
    request: Request,
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
) -> dict:
    """Load anonymous chat history for a portfolio visitor session."""
    await _limit_public_request(request, db, settings, "public_profile_history", 60)
    messages = await list_public_profile_messages(
        db, slug=slug, visitor_session_id=visitor_session_id
    )
    return {"messages": messages}


@router.post("/profiles/{slug}/chat/messages")
async def post_public_profile_chat(
    slug: str,
    body: PublicProfileChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
) -> dict:
    """Send a message to Aarya on a candidate's public portfolio."""
    await _limit_public_request(request, db, settings, "public_profile_chat", 20)
    try:
        return await send_public_profile_message(
            db,
            settings,
            slug=slug,
            visitor_session_id=body.visitor_session_id,
            message=body.message,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles/{slug}/chat/stream")
async def stream_public_profile_chat(
    slug: str,
    body: PublicProfileChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
) -> StreamingResponse:
    """SSE stream for anonymous portfolio chat."""
    await _limit_public_request(request, db, settings, "public_profile_chat", 20)

    async def event_generator():
        async for frame in stream_public_profile_message(
            db,
            settings,
            slug=slug,
            visitor_session_id=body.visitor_session_id,
            message=body.message,
        ):
            yield frame

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/roles/{slug}")
async def get_public_role(slug: str, db=Depends(get_db)) -> dict:
    """World-readable recruiter role when published to the marketplace."""
    role = await fetch_public_role(db, slug)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or not published.")
    return role


@router.post("/roles/{slug}/apply", status_code=201)
async def apply_to_public_role(
    slug: str,
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    resume: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
) -> dict:
    """Inbound apply from public role page — resume parsed and scored vs brief."""
    await _limit_public_request(request, db, settings, "public_role_apply", 8)
    clean_name = full_name.strip()
    clean_email = email.strip().lower()
    if not clean_name or len(clean_name) > 120:
        raise HTTPException(400, detail="Enter your full name.")
    if len(clean_email) > 254 or not _EMAIL_RE.fullmatch(clean_email):
        raise HTTPException(400, detail="Enter a valid email address.")
    role = await fetch_public_role(db, slug)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or not published.")

    file_bytes = await resume.read(MAX_RESUME_BYTES + 1)
    validation_error = validate_resume_upload(resume.content_type, file_bytes)
    if validation_error:
        raise HTTPException(400, detail=validation_error)

    parsed = await asyncio.to_thread(
        parse_resume_bytes,
        file_bytes,
        filename=resume.filename or "resume.pdf",
        mime_type=resume.content_type,
    )
    if not full_name.strip() and parsed.get("full_name"):
        full_name = str(parsed["full_name"])

    try:
        result = await create_inbound_applicant(
            db,
            role_id=uuid.UUID(role["role_id"]),
            full_name=clean_name,
            email=clean_email,
            parsed_profile=parsed,
            source="public_apply",
        )
    except ValueError as exc:
        if str(exc) == "duplicate_apply":
            raise HTTPException(409, detail="You already applied to this role.") from exc
        raise HTTPException(400, detail=str(exc)) from exc

    return result
