"""Integration coverage for the trustworthy career-call schema invariants."""

from __future__ import annotations

import uuid

import asyncpg
import pytest


async def _create_candidate(db_conn: asyncpg.Connection, label: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    email = f"career-schema-{label}-{user_id.hex[:8]}@hireloop.test"
    await db_conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2)",
        user_id,
        email,
    )
    await db_conn.execute(
        """
        INSERT INTO public.users
          (id, email, full_name, role, phone_verified, market, phone_country)
        VALUES ($1, $2, $3, 'candidate', TRUE, 'IN', 'IN')
        """,
        user_id,
        email,
        f"Career Schema {label}",
    )
    return await db_conn.fetchval(
        "INSERT INTO public.candidates (user_id) VALUES ($1) RETURNING id",
        user_id,
    )


@pytest.mark.asyncio
async def test_career_interview_schema_enforces_candidate_ownership_and_safety(
    db_conn: asyncpg.Connection,
) -> None:
    cleanup = db_conn.transaction()
    await cleanup.start()
    try:
        candidate_a = await _create_candidate(db_conn, "A")
        candidate_b = await _create_candidate(db_conn, "B")
        conversation_a = await db_conn.fetchval(
            """
            INSERT INTO public.conversations (candidate_id, title)
            VALUES ($1, 'Candidate A career call')
            RETURNING id
            """,
            candidate_a,
        )
        conversation_b = await db_conn.fetchval(
            """
            INSERT INTO public.conversations (candidate_id, title)
            VALUES ($1, 'Candidate B career call')
            RETURNING id
            """,
            candidate_b,
        )

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            async with db_conn.transaction():
                await db_conn.execute(
                    """
                    INSERT INTO public.voice_sessions
                      (candidate_id, conversation_id, session_type, status)
                    VALUES ($1, $2, 'career_chat', 'scheduled')
                    """,
                    candidate_a,
                    conversation_b,
                )

        valid_session = await db_conn.fetchval(
            """
            INSERT INTO public.voice_sessions
              (candidate_id, conversation_id, session_type, status)
            VALUES ($1, $2, 'career_chat', 'active')
            RETURNING id
            """,
            candidate_a,
            conversation_a,
        )

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            async with db_conn.transaction():
                await db_conn.execute(
                    """
                    INSERT INTO public.career_interview_states
                      (session_id, candidate_id, state)
                    VALUES ($1, $2, '{}'::jsonb)
                    """,
                    valid_session,
                    candidate_b,
                )

        await db_conn.execute(
            """
            INSERT INTO public.career_interview_states
              (session_id, candidate_id, state)
            VALUES ($1, $2, '{}'::jsonb)
            """,
            valid_session,
            candidate_a,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            async with db_conn.transaction():
                await db_conn.execute(
                    """
                    INSERT INTO public.voice_sessions
                      (candidate_id, session_type, status)
                    VALUES ($1, 'career_chat', 'active')
                    """,
                    candidate_a,
                )

        with pytest.raises(asyncpg.CheckViolationError):
            async with db_conn.transaction():
                await db_conn.execute(
                    """
                    INSERT INTO public.voice_sessions
                      (candidate_id, conversation_id, session_type, status, recording_url)
                    VALUES ($1, $2, 'career_chat', 'scheduled', 'forbidden-recording')
                    """,
                    candidate_b,
                    conversation_b,
                )

        state_candidate = await db_conn.fetchval(
            """
            SELECT candidate_id
            FROM public.career_interview_states
            WHERE session_id = $1
            """,
            valid_session,
        )
        assert state_candidate == candidate_a

        await db_conn.execute(
            "DELETE FROM public.conversations WHERE id = $1",
            conversation_a,
        )
        preserved_session = await db_conn.fetchrow(
            """
            SELECT candidate_id, conversation_id
            FROM public.voice_sessions
            WHERE id = $1
            """,
            valid_session,
        )
        assert preserved_session is not None
        assert preserved_session["candidate_id"] == candidate_a
        assert preserved_session["conversation_id"] is None
    finally:
        await cleanup.rollback()
