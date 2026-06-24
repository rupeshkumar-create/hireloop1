"""
Skills vocabulary routes.

GET /api/v1/skills/suggest?q=<query>&limit=<n>
    Autocomplete suggestions from the bundled ~2000-skill canonical vocabulary —
    powers the skills editor on the candidate profile. Auth-gated (any signed-in
    user); read-only and cheap (in-memory lookup, no DB).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from hireloop_api.deps import get_current_user
from hireloop_api.services.skills import suggest_skills

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillSuggestResponse(BaseModel):
    suggestions: list[str]


@router.get("/suggest", response_model=SkillSuggestResponse)
async def suggest(
    q: str = Query("", max_length=80, description="Partial skill text"),
    limit: int = Query(10, ge=1, le=25),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Return canonical skill suggestions for an autocomplete box."""
    return {"suggestions": suggest_skills(q, limit=limit)}
