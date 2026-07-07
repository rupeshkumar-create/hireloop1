"""
Full candidate profile for tailored resume generation.

Merges resume parse, LinkedIn, career_profile, and candidate fields so the LLM
has complete work history and education — without inventing beyond this payload.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

from hireloop_api.services.candidate_intelligence import load_candidate_intelligence


async def load_tailored_resume_profile(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Rich source-of-truth dict for resume tailoring prompts."""
    snapshot = await load_candidate_intelligence(db, candidate_id)
    if snapshot is None:
        return None
    return snapshot.for_resume_tailoring().model_dump(mode="json")
