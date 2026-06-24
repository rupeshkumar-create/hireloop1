"""
Direct chat between a candidate and a recruiter, scoped to one accepted intro.

The intro_request row is the thread. Either party may read once they're on it;
either may post once the intro is 'accepted'. Used by both the candidate
(routes/intros.py) and recruiter (routes/recruiter.py) sides.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg

# Statuses where the thread is open for posting.
_CHATTABLE = ("accepted",)


async def _resolve_party(
    db: asyncpg.Connection, *, intro_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[asyncpg.Record, str]:
    """
    Return (intro_row, sender_type) if `user_id` is a party to the intro.
    Raises ValueError otherwise.
    """
    row = await db.fetchrow(
        """
        SELECT ir.id, ir.status, ir.direction,
               cu.id AS candidate_user_id,
               ru.id AS recruiter_user_id
        FROM public.intro_requests ir
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users cu ON cu.id = c.user_id
        LEFT JOIN public.recruiters rec ON rec.id = ir.recruiter_id
        LEFT JOIN public.users ru ON ru.id = rec.user_id
        WHERE ir.id = $1
        """,
        intro_id,
    )
    if not row:
        raise ValueError("Intro not found")

    if row["candidate_user_id"] == user_id:
        return row, "candidate"
    if row["recruiter_user_id"] == user_id:
        return row, "recruiter"
    raise ValueError("You are not a party to this intro")


async def list_messages(db: asyncpg.Connection, *, intro_id: str, user_id: str) -> dict[str, Any]:
    intro_uuid = uuid.UUID(str(intro_id))
    user_uuid = uuid.UUID(str(user_id))
    intro, sender_type = await _resolve_party(db, intro_id=intro_uuid, user_id=user_uuid)

    rows = await db.fetch(
        """
        SELECT id, sender_type, body, created_at
        FROM public.intro_messages
        WHERE intro_request_id = $1
        ORDER BY created_at ASC
        """,
        intro_uuid,
    )
    return {
        "intro_id": str(intro_uuid),
        "status": intro["status"],
        "can_chat": intro["status"] in _CHATTABLE,
        "you": sender_type,
        "messages": [
            {
                "id": str(r["id"]),
                "sender_type": r["sender_type"],
                "body": r["body"],
                "created_at": r["created_at"].isoformat(),
                "mine": r["sender_type"] == sender_type,
            }
            for r in rows
        ],
    }


async def post_message(
    db: asyncpg.Connection, *, intro_id: str, user_id: str, body: str
) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise ValueError("Message can't be empty")
    if len(text) > 4000:
        text = text[:4000]

    intro_uuid = uuid.UUID(str(intro_id))
    user_uuid = uuid.UUID(str(user_id))
    intro, sender_type = await _resolve_party(db, intro_id=intro_uuid, user_id=user_uuid)

    if intro["status"] not in _CHATTABLE:
        raise PermissionError("This intro hasn't been accepted yet")

    msg_id = uuid.uuid4()
    created = await db.fetchval(
        """
        INSERT INTO public.intro_messages
          (id, intro_request_id, sender_type, sender_user_id, body)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING created_at
        """,
        msg_id,
        intro_uuid,
        sender_type,
        user_uuid,
        text,
    )
    # Touch the intro so both inboxes re-sort to the top.
    await db.execute(
        "UPDATE public.intro_requests SET updated_at = NOW() WHERE id = $1",
        intro_uuid,
    )
    return {
        "id": str(msg_id),
        "sender_type": sender_type,
        "body": text,
        "created_at": created.isoformat(),
        "mine": True,
    }
