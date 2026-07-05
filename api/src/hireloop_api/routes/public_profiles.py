"""Public candidate profiles — no auth required when published."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from hireloop_api.deps import get_db
from hireloop_api.services.career_path_resume import fetch_path_resume_html
from hireloop_api.services.public_profile import fetch_public_profile

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/profiles/{slug}")
async def get_public_profile(slug: str, db=Depends(get_db)) -> dict:
    """World-readable profile when the candidate has published it."""
    profile = await fetch_public_profile(db, slug)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found or not published.")
    return profile


@router.get("/profiles/{slug}/resumes/{resume_id}/download", response_class=HTMLResponse)
async def download_public_path_resume(
    slug: str,
    resume_id: str,
    db=Depends(get_db),
) -> HTMLResponse:
    html = await fetch_path_resume_html(db, resume_id=resume_id, public_slug=slug)
    if not html:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return HTMLResponse(content=html)
