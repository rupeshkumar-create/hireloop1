"""Resolve and persist the candidate's display name (résumé > LinkedIn > profile)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg

from hireloop_api.services.display_name import pick_display_name, sanitize_display_name


async def fetch_primary_resume_full_name(
    db: asyncpg.Connection,
    candidate_id: str,
) -> str | None:
    row = await db.fetchrow(
        """
        SELECT parsed_data
        FROM public.resumes
        WHERE candidate_id = $1::uuid
        ORDER BY is_primary DESC, version DESC, created_at DESC
        LIMIT 1
        """,
        uuid.UUID(candidate_id),
    )
    if not row:
        return None
    parsed = row["parsed_data"]
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (ValueError, TypeError):
            return None
    if not isinstance(parsed, dict):
        return None
    raw = parsed.get("full_name")
    if isinstance(raw, str) and raw.strip():
        return sanitize_display_name(raw.strip())
    return None


def _linkedin_display_name(linkedin_data: object) -> str | None:
    if not isinstance(linkedin_data, dict):
        return None
    for key in ("full_name", "fullName", "name"):
        val = linkedin_data.get(key)
        if isinstance(val, str) and val.strip():
            return sanitize_display_name(val.strip())
    first = linkedin_data.get("first_name") or linkedin_data.get("firstName")
    last = linkedin_data.get("last_name") or linkedin_data.get("lastName")
    if isinstance(first, str) and first.strip():
        joined = first.strip()
        if isinstance(last, str) and last.strip():
            joined = f"{joined} {last.strip()}"
        return joined
    return None


async def resolve_candidate_display_name(
    db: asyncpg.Connection,
    *,
    user_id: str,
    candidate_id: str,
) -> str | None:
    """Best display name for chat salutations and profile_read."""
    user_row = await db.fetchrow(
        """
        SELECT full_name, email
        FROM public.users
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )
    candidate_row = await db.fetchrow(
        """
        SELECT linkedin_data
        FROM public.candidates
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(candidate_id),
    )
    resume_name = await fetch_primary_resume_full_name(db, candidate_id)
    linkedin_raw = candidate_row.get("linkedin_data") if candidate_row else None
    linkedin_name = _linkedin_display_name(linkedin_raw)
    return pick_display_name(
        user_full_name=user_row.get("full_name") if user_row else None,
        email=user_row.get("email") if user_row else None,
        resume_full_name=resume_name,
        linkedin_full_name=linkedin_name,
    )


async def sync_preferred_name_from_resume(
    db: asyncpg.Connection,
    *,
    user_id: str,
    candidate_id: str,
    resume_full_name: str | None,
) -> str | None:
    """
    Sync users.full_name and aarya_state.career_facts.preferred_name when the
    résumé provides an authoritative name (over email-derived or stale chat facts).
    """
    resolved = await resolve_candidate_display_name(
        db,
        user_id=user_id,
        candidate_id=candidate_id,
    )
    name = (resume_full_name or "").strip()
    if name:
        resolved = (
            pick_display_name(
                user_full_name=resolved,
                email=None,
                resume_full_name=name,
            )
            or name
        )

    if not resolved:
        return None

    user_row = await db.fetchrow(
        """
        SELECT full_name, email
        FROM public.users
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )
    current = (user_row["full_name"] or "").strip() if user_row else ""
    if resolved != current:
        await db.execute(
            """
            UPDATE public.users
            SET full_name = $2, updated_at = NOW()
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(user_id),
            resolved,
        )

    row = await db.fetchrow(
        "SELECT aarya_state FROM public.candidates WHERE id = $1::uuid",
        uuid.UUID(candidate_id),
    )
    state: dict[str, Any] = {}
    if row and row["aarya_state"]:
        raw = row["aarya_state"]
        if isinstance(raw, str):
            try:
                state = json.loads(raw)
            except (ValueError, TypeError):
                state = {}
        elif isinstance(raw, dict):
            state = dict(raw)

    facts = state.get("career_facts")
    if not isinstance(facts, dict):
        facts = {}
    else:
        facts = dict(facts)
    if facts.get("preferred_name") != resolved:
        facts["preferred_name"] = resolved
        state["career_facts"] = facts
        await db.execute(
            """
            UPDATE public.candidates
            SET aarya_state = $2::jsonb, updated_at = NOW()
            WHERE id = $1::uuid
            """,
            uuid.UUID(candidate_id),
            json.dumps(state),
        )

    return resolved
