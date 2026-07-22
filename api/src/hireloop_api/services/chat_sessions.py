"""Per-user Aarya conversation helpers — one primary thread, full history."""

from __future__ import annotations

import uuid

import asyncpg
import structlog

logger = structlog.get_logger()


async def _legacy_get_or_create(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
) -> str:
    """Pre-migration conversations table (no user_id / is_primary columns)."""
    row = await db.fetchrow(
        """
        SELECT id
        FROM public.conversations
        WHERE candidate_id = $1::uuid
          AND agent = 'aarya'
          AND deleted_at IS NULL
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        candidate_id,
    )
    if row:
        return str(row["id"])

    convo_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.conversations (id, candidate_id, agent, title)
        VALUES ($1::uuid, $2::uuid, 'aarya', 'Aarya chat')
        """,
        convo_id,
        candidate_id,
    )
    return str(convo_id)


async def get_or_create_primary_conversation(
    db: asyncpg.Connection,
    *,
    user_id: str,
    candidate_id: str,
) -> str:
    """
    Return the candidate's canonical Aarya conversation id (create if missing).
    All chat messages for a user accumulate in this single Supabase thread.
    """
    user_uuid = uuid.UUID(user_id)
    candidate_uuid = uuid.UUID(candidate_id)

    try:
        row = await db.fetchrow(
            """
            SELECT id
            FROM public.conversations
            WHERE candidate_id = $1::uuid
              AND agent = 'aarya'
              AND deleted_at IS NULL
            ORDER BY is_primary DESC, updated_at DESC, created_at DESC
            LIMIT 1
            """,
            candidate_uuid,
        )
        if row:
            convo_id = row["id"]
            await db.execute(
                """
                UPDATE public.conversations
                SET is_primary = TRUE,
                    user_id = $2::uuid,
                    updated_at = NOW()
                WHERE id = $1::uuid
                """,
                convo_id,
                user_uuid,
            )
            return str(convo_id)

        convo_id = uuid.uuid4()
        await db.execute(
            """
            INSERT INTO public.conversations
              (id, candidate_id, user_id, agent, title, is_primary)
            VALUES ($1::uuid, $2::uuid, $3::uuid, 'aarya', 'Aarya chat', TRUE)
            """,
            convo_id,
            candidate_uuid,
            user_uuid,
        )
        return str(convo_id)
    except asyncpg.UndefinedColumnError:
        logger.warning(
            "conversations_primary_columns_missing",
            hint="Run supabase db push for chat user_id/is_primary migration",
        )
        return await _legacy_get_or_create(db, candidate_id=candidate_uuid)


async def load_candidate_chat_messages(
    db: asyncpg.Connection,
    candidate_id: str,
    *,
    limit: int = 60,
) -> list[dict[str, str]]:
    """
    Recent user/assistant turns across every Aarya conversation for this candidate.
    Used by the memory learning loop so preferences survive new sessions.
    """
    rows = await db.fetch(
        """
        SELECT m.role, m.content
        FROM public.messages m
        JOIN public.conversations c ON c.id = m.conversation_id
        WHERE c.candidate_id = $1::uuid
          AND c.agent = 'aarya'
          AND c.deleted_at IS NULL
          AND m.role IN ('user', 'assistant')
          AND m.voice_session_id IS NULL
        ORDER BY m.created_at DESC
        LIMIT $2
        """,
        uuid.UUID(candidate_id),
        limit,
    )
    chronological = list(reversed(rows))
    return [{"role": r["role"], "content": r["content"] or ""} for r in chronological]
