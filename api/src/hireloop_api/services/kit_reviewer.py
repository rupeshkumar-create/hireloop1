"""
Drafter-reviewer pass for application kit text assets.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings

logger = structlog.get_logger()

REVIEWER_SYSTEM = """You are a hiring-manager reviewer critiquing a job application kit.
Return ONLY valid JSON:
{
  "approved": false,
  "issues": ["..."],
  "cover_letter": "revised cover letter or empty if approved",
  "interview_prep": "revised markdown prep or empty if approved",
  "reviewer_notes": "2-3 bullet critique for the candidate"
}
Rules:
- Verify keywords from the job appear naturally (never stuffed)
- Flag generic phrases ("team player", "fast learner" without evidence)
- Interview prep must reference the candidate's REAL experience only
- If drafts are good, set approved=true and leave cover_letter/interview_prep empty
"""


def _reviewer_llm(settings: Settings) -> ChatOpenAI:
    model = settings.openrouter_fallback_model or settings.openrouter_primary_model
    return ChatOpenAI(
        model=model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.25,
        max_tokens=2048,
        default_headers={
            "HTTP-Referer": "https://hireschema.com",
            "X-Title": "Hireschema - Kit Reviewer",
        },
    )


async def review_and_revise_kit_text(
    *,
    settings: Settings,
    profile: dict[str, Any],
    job: dict[str, Any],
    cover_letter: str,
    interview_prep: str,
) -> tuple[str, str, str]:
    """Second-pass reviewer; returns (cover, prep, reviewer_notes)."""
    if not settings.openrouter_api_key:
        return cover_letter, interview_prep, ""

    llm = _reviewer_llm(settings)
    payload = {
        "job": {
            "title": job.get("title"),
            "company": job.get("company_name"),
            "skills_required": (job.get("skills_required") or [])[:12],
            "description_excerpt": str(job.get("description") or "")[:2500],
        },
        "candidate": {
            "name": profile.get("full_name"),
            "title": profile.get("current_title"),
            "skills": (profile.get("skills") or [])[:15],
        },
        "draft_cover_letter": cover_letter[:4000],
        "draft_interview_prep": interview_prep[:4000],
    }
    try:
        resp = await llm.ainvoke(
            [
                SystemMessage(content=REVIEWER_SYSTEM),
                HumanMessage(content=json.dumps(payload, default=str)),
            ]
        )
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(raw)
        if not isinstance(data, dict):
            return cover_letter, interview_prep, ""

        notes = str(data.get("reviewer_notes") or "").strip()
        if data.get("approved"):
            return cover_letter, interview_prep, notes

        new_cover = str(data.get("cover_letter") or "").strip() or cover_letter
        new_prep = str(data.get("interview_prep") or "").strip() or interview_prep
        from hireloop_api.services.application_kit import normalize_application_text_assets

        new_cover, new_prep = normalize_application_text_assets(
            cover_letter=new_cover,
            interview_prep=new_prep,
            profile=profile,
            job=job,
        )
        return new_cover, new_prep, notes
    except Exception as exc:
        logger.warning("kit_reviewer_failed", error=str(exc)[:200])
        return cover_letter, interview_prep, ""
