"""Public candidate profiles — no auth required when published."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_current_user_optional, get_db
from hireloop_api.services.public_profile import fetch_public_profile
from hireloop_api.services.public_profile_chat import (
    list_public_profile_messages,
    send_public_profile_message,
    stream_public_profile_message,
)
from hireloop_api.services.public_role import fetch_public_role

logger = structlog.get_logger()

router = APIRouter(prefix="/public", tags=["public"])


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
    db=Depends(get_db),
) -> dict:
    """Load anonymous chat history for a portfolio visitor session."""
    messages = await list_public_profile_messages(
        db, slug=slug, visitor_session_id=visitor_session_id
    )
    return {"messages": messages}


@router.post("/profiles/{slug}/chat/messages")
async def post_public_profile_chat(
    slug: str,
    body: PublicProfileChatRequest,
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
) -> dict:
    """Send a message to Aarya on a candidate's public portfolio."""
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
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
) -> StreamingResponse:
    """SSE stream for anonymous portfolio chat."""

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
