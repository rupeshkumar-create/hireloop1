"""Public candidate profiles — no auth required when published."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from hireloop_api.deps import get_db
from hireloop_api.services.public_profile import fetch_public_profile
from hireloop_api.services.public_role import fetch_public_role

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/profiles/{slug}")
async def get_public_profile(slug: str, db=Depends(get_db)) -> dict:
    """World-readable profile when the candidate has published it."""
    profile = await fetch_public_profile(db, slug)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found or not published.")
    return profile


@router.get("/roles/{slug}")
async def get_public_role(slug: str, db=Depends(get_db)) -> dict:
    """World-readable recruiter role when published to the marketplace."""
    role = await fetch_public_role(db, slug)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found or not published.")
    return role
