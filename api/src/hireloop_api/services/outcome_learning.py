"""
Outcome recording + light calibration hints for Aarya recommendations.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()

_VALID_STAGES = frozenset(
    {"applied", "screening", "interview", "offer", "rejected", "ghosted", "withdrawn"}
)

_POSITIVE_STAGES = frozenset({"screening", "interview", "offer"})
_NEGATIVE_STAGES = frozenset({"rejected", "ghosted"})


async def record_application_outcome(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    stage: str,
    notes: str | None = None,
    dossier_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in _VALID_STAGES:
        return {"error": f"Invalid stage: {stage}"}

    await db.execute(
        """
        INSERT INTO public.application_outcomes
          (candidate_id, job_id, stage, notes, dossier_snapshot, updated_at)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, NOW())
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          stage = EXCLUDED.stage,
          notes = EXCLUDED.notes,
          dossier_snapshot = COALESCE(EXCLUDED.dossier_snapshot, application_outcomes.dossier_snapshot),
          updated_at = NOW()
        """,
        candidate_id,
        job_id,
        stage,
        notes,
        json.dumps(dossier_snapshot) if dossier_snapshot else None,
    )

    await _update_calibration_hints(db, candidate_id=candidate_id, job_id=job_id, stage=stage)
    return {"ok": True, "stage": stage}


async def _update_calibration_hints(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    stage: str,
) -> None:
    """Store lightweight outcome patterns in profile_enrichment for Aarya context."""
    if stage not in _POSITIVE_STAGES and stage not in _NEGATIVE_STAGES:
        return

    job = await db.fetchrow(
        """
        SELECT j.title, co.name AS company_name
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.id = $1::uuid
        """,
        job_id,
    )
    if not job:
        return

    row = await db.fetchrow(
        "SELECT profile_enrichment FROM public.candidates WHERE id = $1::uuid",
        candidate_id,
    )
    enrich = row["profile_enrichment"] if row and row["profile_enrichment"] else {}
    if not isinstance(enrich, dict):
        enrich = {}

    hints = list(enrich.get("outcome_hints") or [])
    hint = {
        "title": job["title"],
        "company": job.get("company_name"),
        "stage": stage,
        "signal": "positive" if stage in _POSITIVE_STAGES else "negative",
    }
    hints = [hint, *[h for h in hints if h.get("title") != hint["title"]]][:19]
    enrich["outcome_hints"] = hints

    await db.execute(
        """
        UPDATE public.candidates
        SET profile_enrichment = $2::jsonb, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        candidate_id,
        json.dumps(enrich),
    )


def build_kit_aware_interview_prep(
    *,
    base_prep: str,
    dossier: dict[str, Any] | None,
    job: dict[str, Any],
    profile: dict[str, Any],
    intro_status: str | None = None,
) -> str:
    """Enrich interview prep with submitted kit + intro context."""
    lines = [base_prep.strip()]
    submitted = (dossier or {}).get("submitted") or {}
    if submitted.get("cover_letter"):
        excerpt = str(submitted["cover_letter"])[:400].replace("\n", " ")
        lines.append(
            "\n## What you told them (cover letter excerpt)\n"
            f"> {excerpt}…\n"
            "Expect questions that probe claims from this letter — rehearse proof points."
        )
    ats = (dossier or {}).get("ats_report") or {}
    gaps = ats.get("keywords_gap") or []
    if gaps:
        lines.append(
            "\n## Honest gaps to prepare for\n"
            + "\n".join(f"- {g}" for g in gaps[:6])
            + "\n\nBridge answers: adjacent experience + learning plan — never invent."
        )
    raw_enrich = profile.get("profile_enrichment")
    enrich = raw_enrich if isinstance(raw_enrich, dict) else {}
    stars = enrich.get("star_stories") or []
    if stars:
        lines.append("\n## Your STAR bank\n" + "\n".join(f"- {s}" for s in stars[:4]))

    if intro_status in ("sent", "opened", "replied"):
        lines.append(
            f"\n## Intro status: {intro_status}\n"
            "They may have seen your Hireschema intro — align stories with what Nitya sent."
        )
    lines.append(
        f"\n## Role focus\n{job.get('title')} at {job.get('company_name') or 'the company'}"
    )
    return "\n".join(lines).strip()
