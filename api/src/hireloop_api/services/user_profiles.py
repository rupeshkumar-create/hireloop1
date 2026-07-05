"""Read-only checks for candidate / recruiter profile rows on one login."""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def user_has_candidate_profile(
    db: asyncpg.Connection,
    user_id: UUID,
) -> bool:
    return bool(
        await db.fetchval(
            """
            SELECT 1 FROM public.candidates
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            user_id,
        )
    )


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


async def user_profile_flags(
    db: asyncpg.Connection,
    user_id: UUID,
) -> tuple[bool, bool]:
    row = await db.fetchrow(
        """
        SELECT
          EXISTS (
            SELECT 1 FROM public.candidates
            WHERE user_id = $1::uuid AND deleted_at IS NULL
          ) AS has_candidate,
          EXISTS (
            SELECT 1 FROM public.recruiters
            WHERE user_id = $1::uuid AND deleted_at IS NULL
          ) AS has_recruiter
        """,
        user_id,
    )
    if not row:
        return False, False
    return bool(row["has_candidate"]), bool(row["has_recruiter"])
