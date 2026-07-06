"""Public candidate profiles — no auth required when published."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db
from hireloop_api.services.public_profile import fetch_public_profile
from hireloop_api.services.public_profile_chat import (
    list_public_profile_messages,
    send_public_profile_message,
)
from hireloop_api.services.public_role import fetch_public_role

router = APIRouter(prefix="/public", tags=["public"])


class PublicProfileChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    visitor_session_id: uuid.UUID


@router.get("/profiles/{slug}")
async def get_public_profile(slug: str, db=Depends(get_db)) -> dict:
    """World-readable profile when the candidate has published it."""
    profile = await fetch_public_profile(db, slug)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found or not published.")
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


@router.get("/roles/{slug}")
async def get_public_role(slug: str, db=Depends(get_db)) -> dict:
    """World-readable recruiter role when published to the marketplace."""
    role = await fetch_public_role(db, slug)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or not published.")
    return role
