"""
JD enrichment (backend plan #30) — extract structure from a job description.

ATS feeds (Greenhouse/Lever) and some scrapes arrive with a rich description but
NO structured `skills_required` / seniority / CTC — which caps match quality,
because the matcher's skill-overlap and seniority signals have nothing to work
with. One cheap LLM pass per job reads the description and fills those fields.

Runs as a backfill (scripts/enrich_jobs.py), off the hot ingest path. Degrades
gracefully: no key or any failure → returns None and the job is left as-is.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from hireloop_api.config import Settings
from hireloop_api.services.resume_parser import _normalise_skill_list

logger = structlog.get_logger()

_VALID_SENIORITY = {"intern", "junior", "mid", "senior", "lead", "director", "vp", "c_level"}
_MAX_SKILLS = 15

_SYSTEM_PROMPT = """You extract structured hiring signals from a job description.
Return ONLY valid JSON (no markdown, no prose) with exactly this shape:
{
  "skills_required": [string],   // concrete skills/tools/competencies, lowercase, max 15
  "seniority": "intern"|"junior"|"mid"|"senior"|"lead"|"director"|"vp"|"c_level"|null,
  "ctc_min": integer|null,       // INR per annum if a salary is stated, else null
  "ctc_max": integer|null
}
Rules:
- skills_required: real skills only (e.g. "python", "product management", "pbm",
  "stakeholder management"). No sentences, no soft filler ("team player"), no
  section words ("responsibilities"). Deduplicate.
- seniority: infer from title/requirements (years of experience). null if unclear.
- CTC only when the JD states pay; convert LPA/lakh to absolute INR per annum
  (e.g. "25 LPA" -> 2500000). null otherwise. Never invent numbers."""


def _parse_enrichment(content: str) -> dict[str, Any] | None:
    """Parse + validate the LLM JSON into a clean enrichment dict, or None."""
    if not content:
        return None
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict):
        return None

    # Skills → the parser's normalizer: readable display form, deduped, with the
    # same artifact filter (drops "i personally:", "languages", fragments) so a
    # JD's extracted skills are as clean as a résumé's.
    skills = _normalise_skill_list(obj.get("skills_required"))

    seniority = obj.get("seniority")
    seniority = seniority if seniority in _VALID_SENIORITY else None

    def _pos_int(v: object) -> int | None:
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return n if 10_000 <= n <= 100_000_000 else None

    return {
        "skills_required": skills[:_MAX_SKILLS],
        "seniority": seniority,
        "ctc_min": _pos_int(obj.get("ctc_min")),
        "ctc_max": _pos_int(obj.get("ctc_max")),
    }


async def enrich_job_description(
    title: str, description: str, settings: Settings
) -> dict[str, Any] | None:
    """Run one LLM pass over a JD. Returns the validated enrichment or None."""
    if not settings.openrouter_api_key or not (description or "").strip():
        return None
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.openrouter_fallback_model,  # cheap model — bulk backfill
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.1,
        max_tokens=500,
        timeout=20,
        default_headers={
            "HTTP-Referer": "https://hireschema.com",
            "X-Title": "Hireschema - JD Enrichment",
        },
    )
    user = f"TITLE: {title}\n\nDESCRIPTION:\n{description[:6000]}"
    try:
        resp = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user)]
        )
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as exc:  # never break a backfill batch
        logger.warning("jd_enrichment_llm_failed", error=str(exc)[:200])
        return None
    return _parse_enrichment(content)
