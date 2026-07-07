"""Candidate opt-in for tailored resume generation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import asyncpg


def tailored_resume_enabled(candidate: Mapping[str, Any] | None) -> bool:
    """True when the candidate has opted in to tailored resumes."""
    if not candidate:
        return False
    return bool(candidate.get("tailored_resume_enabled"))


async def fetch_tailored_resume_enabled(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> bool:
    row = await db.fetchrow(
        """
        SELECT tailored_resume_enabled
        FROM public.candidates
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        candidate_id,
    )
    return bool(row["tailored_resume_enabled"]) if row else False
