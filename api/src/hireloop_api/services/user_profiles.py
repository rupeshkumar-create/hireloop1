"""Read-only checks for candidate / recruiter profile rows on one login."""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def user_has_recruiter_profile(
    db: asyncpg.Connection,
    user_id: UUID,
) -> bool:
    return bool(
        await db.fetchval(
            """
            SELECT 1 FROM public.recruiters
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            user_id,
        )
    )


async def user_has_registered_candidate_profile(
    db: asyncpg.Connection,
    user_id: UUID,
) -> bool:
    """
    True when this login intentionally registered as a candidate.

    Recruiter-only accounts may get an auto-provisioned candidates stub when
    candidate APIs are hit; those stubs must not unlock role switching.
    """
    row = await db.fetchrow(
        """
        SELECT
          c.id AS candidate_id,
          c.onboarding_complete,
          c.profile_complete,
          c.linkedin_url,
          u.role AS user_role
        FROM public.users u
        LEFT JOIN public.candidates c
          ON c.user_id = u.id AND c.deleted_at IS NULL
        WHERE u.id = $1::uuid AND u.deleted_at IS NULL
        """,
        user_id,
    )
    if not row or not row["candidate_id"]:
        return False

    if row["onboarding_complete"] or row["profile_complete"]:
        return True
    if row["linkedin_url"]:
        return True

    candidate_id = row["candidate_id"]
    has_resume = await db.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM public.resumes r
          WHERE r.candidate_id = $1::uuid
        )
        """,
        candidate_id,
    )
    if has_resume:
        return True

    has_voice = await db.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM public.voice_sessions vs
          WHERE vs.candidate_id = $1::uuid AND vs.status = 'completed'
        )
        """,
        candidate_id,
    )
    if has_voice:
        return True

    # Recruiter-primary logins with only an empty stub are not candidate-registered.
    if row["user_role"] == "recruiter":
        return False

    # Candidate-primary bootstrap row (may still be onboarding).
    return True


async def user_has_candidate_profile(
    db: asyncpg.Connection,
    user_id: UUID,
) -> bool:
    return await user_has_registered_candidate_profile(db, user_id)


async def user_profile_flags(
    db: asyncpg.Connection,
    user_id: UUID,
) -> tuple[bool, bool]:
    has_candidate = await user_has_registered_candidate_profile(db, user_id)
    has_recruiter = await user_has_recruiter_profile(db, user_id)
    return has_candidate, has_recruiter
