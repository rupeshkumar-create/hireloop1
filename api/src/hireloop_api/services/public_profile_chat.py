"""Anonymous portfolio chat — Aarya answers about a published candidate profile."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings
from hireloop_api.services.chat_stream import sse_chips, sse_done, sse_status, sse_text
from hireloop_api.services.public_profile import fetch_public_profile
from hireloop_api.services.rate_limit import check_rate_limit

logger = structlog.get_logger()

_MAX_HISTORY = 12
_MAX_MESSAGE_LEN = 2000

_DEFAULT_CHIPS = [
    {
        "id": "roles",
        "label": "What roles are they open to?",
        "message": "What roles are they open to?",
    },
    {
        "id": "summary",
        "label": "Summarize for my hiring manager",
        "message": "Summarize this candidate in 3 bullets for a hiring manager.",
    },
    {
        "id": "intro",
        "label": "Request intro",
        "message": "How do I request an intro to this candidate on Hireschema?",
    },
]


async def _resolve_candidate_id(db: asyncpg.Connection, slug: str) -> uuid.UUID | None:
    row = await db.fetchval(
        """
        SELECT c.id
        FROM public.candidates c
        WHERE c.public_slug = $1
          AND c.public_profile_enabled = TRUE
          AND c.deleted_at IS NULL
        """,
        slug.strip(),
    )
    return uuid.UUID(str(row)) if row else None


def _profile_context(profile: dict[str, Any]) -> str:
    """Compact JSON for the LLM — only fields already world-readable."""
    payload = {
        "display_name": profile.get("display_name"),
        "headline": profile.get("headline"),
        "summary": profile.get("summary"),
        "current_title": profile.get("current_title"),
        "current_company": profile.get("current_company"),
        "years_experience": profile.get("years_experience"),
        "location_city": profile.get("location_city"),
        "location_state": profile.get("location_state"),
        "looking_for": profile.get("looking_for"),
        "skills": profile.get("skills") or [],
        "experience": profile.get("experience") or [],
        "education": profile.get("education") or [],
        "contact_hidden": bool(profile.get("contact", {}).get("hidden")),
        "has_email": bool(profile.get("contact", {}).get("email")),
        "has_phone": bool(profile.get("contact", {}).get("phone")),
        "linkedin_visible": bool(profile.get("linkedin_url")),
    }
    return json.dumps(payload, ensure_ascii=False)


def _system_prompt(profile: dict[str, Any]) -> str:
    name = profile.get("display_name") or profile.get("headline") or "this candidate"
    return f"""You are Aarya, the AI assistant on {name}'s Hireschema public portfolio.

Adapt to visitor intent:
- Recruiter / hiring manager: pitch fit, suggest signing up on Hireschema to request an intro,
  offer to compare against a pasted job description. Never share hidden contact details.
- Peer / network: give a shareable summary of strengths — no private contact info.
- Job seeker: clarify this is {name}'s page; for their own search they should sign up at Hireschema.

Answer questions about background, skills, experience, and target roles using ONLY the public
profile JSON provided — never invent employers, dates, or skills.
If you do not know something, say it is not on the public profile.

Tone: warm, concise, professional. 2–4 short paragraphs max unless listing skills or roles.
Never share private contact details when contact_hidden is true."""


async def _get_or_create_chat(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    visitor_session_id: uuid.UUID,
) -> uuid.UUID:
    row = await db.fetchrow(
        """
        INSERT INTO public.public_profile_chats (candidate_id, visitor_session_id)
        VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (candidate_id, visitor_session_id)
        DO UPDATE SET updated_at = NOW()
        RETURNING id
        """,
        candidate_id,
        visitor_session_id,
    )
    return uuid.UUID(str(row["id"]))


async def list_public_profile_messages(
    db: asyncpg.Connection,
    *,
    slug: str,
    visitor_session_id: uuid.UUID,
) -> list[dict[str, Any]]:
    candidate_id = await _resolve_candidate_id(db, slug)
    if not candidate_id:
        return []

    chat_id = await db.fetchval(
        """
        SELECT id FROM public.public_profile_chats
        WHERE candidate_id = $1::uuid AND visitor_session_id = $2::uuid
        """,
        candidate_id,
        visitor_session_id,
    )
    if not chat_id:
        return []

    rows = await db.fetch(
        """
        SELECT role, content, created_at
        FROM public.public_profile_chat_messages
        WHERE chat_id = $1::uuid
        ORDER BY created_at ASC
        LIMIT 50
        """,
        chat_id,
    )
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


async def _prepare_public_chat_turn(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    slug: str,
    visitor_session_id: uuid.UUID,
    message: str,
) -> tuple[dict[str, Any], uuid.UUID, uuid.UUID, list[Any], ChatOpenAI | None]:
    text = message.strip()
    if not text:
        raise ValueError("Message required")
    if len(text) > _MAX_MESSAGE_LEN:
        raise ValueError("Message too long")

    profile = await fetch_public_profile(db, slug)
    if not profile:
        raise LookupError("Profile not found")

    candidate_id = await _resolve_candidate_id(db, slug)
    if not candidate_id:
        raise LookupError("Profile not found")

    await check_rate_limit(
        str(visitor_session_id),
        "public_profile_chat",
        max_per_hour=40,
        db=db,
    )

    chat_id = await _get_or_create_chat(
        db,
        candidate_id=candidate_id,
        visitor_session_id=visitor_session_id,
    )

    await db.execute(
        """
        INSERT INTO public.public_profile_chat_messages (chat_id, role, content)
        VALUES ($1::uuid, 'user', $2)
        """,
        chat_id,
        text,
    )

    history_rows = await db.fetch(
        """
        SELECT role, content
        FROM public.public_profile_chat_messages
        WHERE chat_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        chat_id,
        _MAX_HISTORY,
    )
    history = list(reversed(history_rows))

    llm = None
    if settings.openrouter_api_key:
        llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.35,
            max_tokens=600,
            streaming=True,
            default_headers={
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Public Portfolio Chat",
            },
        )

    messages = [
        SystemMessage(
            content=_system_prompt(profile)
            + "\n\nPublic profile JSON:\n"
            + _profile_context(profile)
        ),
    ]
    for row in history:
        if row["role"] == "user":
            messages.append(HumanMessage(content=row["content"]))
        elif row["role"] == "assistant":
            messages.append(AIMessage(content=row["content"]))

    return profile, candidate_id, chat_id, messages, llm


async def stream_public_profile_message(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    slug: str,
    visitor_session_id: uuid.UUID,
    message: str,
) -> AsyncIterator[str]:
    """SSE stream for anonymous portfolio chat."""
    try:
        _profile, _candidate_id, chat_id, messages, llm = await _prepare_public_chat_turn(
            db,
            settings,
            slug=slug,
            visitor_session_id=visitor_session_id,
            message=message,
        )
    except (LookupError, ValueError) as exc:
        yield sse_text(str(exc))
        yield sse_done()
        return

    yield sse_status("Reading their public profile…")
    reply_parts: list[str] = []
    fallback = (
        "Thanks for your interest! I'm having trouble connecting right now — "
        "please try again in a moment or sign up on Hireschema to connect directly."
    )

    if llm is None:
        yield sse_text(fallback)
    else:
        try:
            async for chunk in llm.astream(messages):
                piece = (
                    chunk.content if isinstance(chunk.content, str) else str(chunk.content or "")
                )
                if not piece:
                    continue
                reply_parts.append(piece)
                yield sse_text(piece)
        except Exception as exc:
            logger.warning("public_profile_chat_stream_failed", error=str(exc)[:200])
            if not reply_parts:
                yield sse_text(fallback)
                reply_parts = [fallback]

    reply = "".join(reply_parts).strip() or fallback
    await db.execute(
        """
        INSERT INTO public.public_profile_chat_messages (chat_id, role, content)
        VALUES ($1::uuid, 'assistant', $2)
        """,
        chat_id,
        reply,
    )
    yield sse_chips(_DEFAULT_CHIPS)
    yield sse_done()


async def send_public_profile_message(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    slug: str,
    visitor_session_id: uuid.UUID,
    message: str,
) -> dict[str, Any]:
    """Non-streaming fallback — aggregates the SSE stream."""
    chunks: list[str] = []
    async for frame in stream_public_profile_message(
        db,
        settings,
        slug=slug,
        visitor_session_id=visitor_session_id,
        message=message,
    ):
        if '"text":' in frame:
            try:
                payload = json.loads(frame.removeprefix("data: ").strip())
                if payload.get("text"):
                    chunks.append(str(payload["text"]))
            except json.JSONDecodeError:
                pass
    reply = "".join(chunks).strip()
    return {
        "reply": reply,
        "messages": await list_public_profile_messages(
            db, slug=slug, visitor_session_id=visitor_session_id
        ),
    }
