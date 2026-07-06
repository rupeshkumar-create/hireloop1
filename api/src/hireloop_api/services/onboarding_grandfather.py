"""Grandfather pre-wizard candidates who already activated their profile."""

from typing import Any

import asyncpg


def _has_meaningful_profile(candidate: asyncpg.Record | dict[str, Any]) -> bool:
    title = str(candidate.get("current_title") or "").strip()
    skills = candidate.get("skills") or []
    skill_count = len([s for s in skills if str(s).strip()])
    looking_for = str(candidate.get("looking_for") or "").strip()
    if candidate.get("profile_complete") is True:
        return True
    return bool(title and (skill_count > 0 or looking_for))


async def maybe_grandfather_onboarding_complete(
    db: asyncpg.Connection,
    *,
    candidate: asyncpg.Record | dict[str, Any],
) -> bool:
    """Return True when onboarding is complete (possibly after auto-heal)."""
    if candidate.get("onboarding_complete") is True:
        return True

    if not _has_meaningful_profile(candidate):
        return False

    has_resume = await db.fetchval(
        """
        SELECT 1
        FROM public.resumes
        WHERE candidate_id = $1::uuid
        LIMIT 1
        """,
        candidate["id"],
    )

    # Resume + parsed profile is enough for legacy accounts created before the flag.
    if not has_resume and not candidate.get("profile_complete"):
        return False

    await db.execute(
        """
        UPDATE public.candidates
        SET onboarding_complete = TRUE, updated_at = NOW()
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        candidate["id"],
    )
    return True
