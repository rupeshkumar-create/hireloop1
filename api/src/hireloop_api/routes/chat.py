"""
Chat routes — Aarya agent interaction endpoints.

POST /api/v1/chat/sessions           → create new conversation
GET  /api/v1/chat/sessions           → list candidate's conversations
POST /api/v1/chat/sessions/{id}/messages  → send message, stream response
GET  /api/v1/chat/sessions/{id}/messages  → get message history
GET  /api/v1/chat/sessions/{id}/actions   → get agent actions (UI counter)
"""

import json
import re
import uuid
from collections.abc import AsyncIterator

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from starlette.background import BackgroundTask

from hireloop_api.agents.aarya import tools as aarya_tools
from hireloop_api.agents.aarya.agent import (
    AaryaState,
    _detect_hinglish,
    _detect_likely_intent,
    get_aarya_graph,
)
from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import (
    coerce_uuid,
    get_db,
    get_db_pool,
    get_phone_verified_user,
    serialize_row,
)
from hireloop_api.market_db import fetch_candidate_market
from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.services.candidate_display_name import resolve_candidate_display_name
from hireloop_api.services.career_intelligence import CareerIntelligenceService
from hireloop_api.services.career_path import CareerPathService
from hireloop_api.services.career_path_selection import (
    career_path_options,
    extract_find_role_and_city,
    resolve_job_search_query,
    try_apply_career_path_selection,
)
from hireloop_api.services.chat_sessions import get_or_create_primary_conversation
from hireloop_api.services.chat_stream import (
    sse_done,
    sse_error,
    sse_jobs,
    sse_status,
    sse_text,
)
from hireloop_api.services.job_search_refresh import (
    fetch_shown_job_ids,
    wants_fresh_job_results,
)
from hireloop_api.services.matching import MatchingEngine
from hireloop_api.services.memory import (
    CandidateMemoryService,
    format_known_facts,
    run_memory_update,
)
from hireloop_api.services.ranking import dedupe_jobs
from hireloop_api.services.rate_limit import check_rate_limit
from hireloop_api.services.tool_cache import clear_session_tool_cache

logger = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])
_JOB_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# Live status labels streamed to the chat UI while tools run (R7).
_TEXT_TOOL_STATUS_LABELS: dict[str, str] = {
    "profile_read": "Reading your profile…",
    "build_career_path": "Mapping your career path…",
    "job_search": "Searching roles in your market…",
    "get_match_score": "Scoring this role…",
    "match_score": "Scoring this role…",
    "save_job": "Saving this role…",
    "prepare_application_kit": "Preparing your application kit…",
    "request_intro": "Preparing your intro…",
    "direct_apply": "Logging your application…",
    "update_job_preferences": "Updating your filters…",
    "update_profile": "Updating your profile…",
}

_VOICE_TOOL_STATUS_LABELS: dict[str, str] = {
    "profile_read": "I'm checking your profile…",
    "build_career_path": "I'm mapping the best next steps…",
    "job_search": "I'm searching roles in your market now…",
    "get_match_score": "I'm checking the fit for this role…",
    "match_score": "I'm checking the fit for this role…",
    "save_job": "I'm saving that role…",
    "prepare_application_kit": "I'm building your apply kit…",
    "request_intro": "I'm preparing the intro request…",
    "direct_apply": "I'm logging that application…",
    "update_job_preferences": "I'm updating your filters…",
    "update_profile": "I'm updating your profile…",
}

# Spoken filler clips + ETA for voice UX (synced to SSE status events).
_TOOL_STATUS_META: dict[str, dict[str, str | int]] = {
    "profile_read": {
        "spoken": "Let me check your profile.",
        "eta_sec": 4,
        "text": _TEXT_TOOL_STATUS_LABELS["profile_read"],
        "voice": _VOICE_TOOL_STATUS_LABELS["profile_read"],
    },
    "build_career_path": {
        "spoken": "I'm mapping your career path.",
        "eta_sec": 6,
        "text": _TEXT_TOOL_STATUS_LABELS["build_career_path"],
        "voice": _VOICE_TOOL_STATUS_LABELS["build_career_path"],
    },
    "job_search": {
        "spoken": "I'm searching roles in your market for you.",
        "eta_sec": 8,
        "text": _TEXT_TOOL_STATUS_LABELS["job_search"],
        "voice": _VOICE_TOOL_STATUS_LABELS["job_search"],
    },
    "get_match_score": {
        "spoken": "Let me score this role for you.",
        "eta_sec": 5,
        "text": _TEXT_TOOL_STATUS_LABELS["get_match_score"],
        "voice": _VOICE_TOOL_STATUS_LABELS["get_match_score"],
    },
    "prepare_application_kit": {
        "spoken": "I'm preparing your application kit.",
        "eta_sec": 10,
        "text": _TEXT_TOOL_STATUS_LABELS["prepare_application_kit"],
        "voice": _VOICE_TOOL_STATUS_LABELS["prepare_application_kit"],
    },
    "update_profile": {
        "spoken": "I'm updating your profile.",
        "eta_sec": 3,
        "text": _TEXT_TOOL_STATUS_LABELS["update_profile"],
        "voice": _VOICE_TOOL_STATUS_LABELS["update_profile"],
    },
}


def _agent_message_text(content: object) -> str:
    """Extract user-visible text from an AIMessage content field (str or blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif "text" in block:
                    parts.append(str(block["text"]))
        return "".join(parts)
    return str(content) if content else ""


def _extract_application_kit_job_ids(text: str) -> list[str]:
    """Return explicit job UUIDs from an application-kit request, preserving order."""
    return list(dict.fromkeys(match.group(0).lower() for match in _JOB_UUID_RE.finditer(text)))[:3]


def _build_application_kit_reply(result: dict) -> str:
    """Compact deterministic reply after preparing application-kit assets."""
    kits = result.get("kits") if isinstance(result, dict) else None
    errors = result.get("errors") if isinstance(result, dict) else None
    ready = kits if isinstance(kits, list) else []
    failed = errors if isinstance(errors, list) else []

    if ready:
        first = ready[0] if isinstance(ready[0], dict) else {}
        job = first.get("job") if isinstance(first.get("job"), dict) else {}
        title = str(job.get("title") or "the role")
        company = str(job.get("company_name") or "the company")
        count_text = (
            f"Your application kit is ready for **{title}** at **{company}**."
            if len(ready) == 1
            else f"I prepared {len(ready)} application kits."
        )
        tail = (
            "\n\nI added the cards below so you can preview and download the tailored resume, "
            "cover letter, and interview prep from here."
        )
        if failed:
            tail += "\n\nA few roles could not be prepared; try those again in a moment."
        return count_text + tail

    if failed:
        first_error = failed[0] if isinstance(failed[0], dict) else {}
        message = str(first_error.get("error") or "the kit could not be prepared")
        return f"I couldn't prepare that application kit yet: {message}. Please try again in a moment."

    return "I couldn't prepare that application kit yet. Please try again in a moment."


def _looks_incomplete_profile_reply(text: str) -> bool:
    """True when Aarya stopped after a pre-tool line without actual gap advice."""
    t = text.strip()
    if not t:
        return True
    lowered = t.lower()
    if "what i found" in lowered and "what i recommend" in lowered:
        return False
    if re.search(r"let me (pull|read|check)", lowered):
        has_advice = "what i recommend" in lowered or bool(re.search(r"\n\d+\.\s+", t))
        return not has_advice
    return len(t) < 60


def _build_profile_gap_reply(open_questions: list[str]) -> str:
    """Deterministic fallback when the LLM omits post-profile_read advice."""
    if open_questions:
        lines = [
            "**What I found**",
            "A few profile gaps are holding back match quality.",
            "",
            "**What I recommend**",
        ]
        for i, question in enumerate(open_questions[:4], 1):
            lines.append(f"{i}. {question}")
        lines.extend(
            [
                "",
                "**What you can do next**",
                "Reply with any one answer above and I'll save it to your profile.",
            ]
        )
        return "\n".join(lines)

    return (
        "**What I found**\n"
        "Your profile has the basics, but key matching fields are still empty.\n\n"
        "**What I recommend**\n"
        "1. Add your expected CTC range (LPA) so I can filter salary-fit roles.\n"
        "2. List your top skills so semantic matching works better.\n"
        "3. Add notice period and preferred work mode (remote/hybrid/onsite).\n\n"
        "**What you can do next**\n"
        "Tell me your target CTC and notice period — I'll update your profile."
    )


def tool_status_label(tool_name: str, *, voice_mode: bool = False) -> str:
    """Return the user-facing live status for a tool call."""
    meta = _TOOL_STATUS_META.get(tool_name)
    if meta:
        base = str(meta["voice" if voice_mode else "text"])
        eta = meta.get("eta_sec")
        if isinstance(eta, int):
            return f"{base.rstrip('…')} (~{eta}s)…"
        return base
    labels = _VOICE_TOOL_STATUS_LABELS if voice_mode else _TEXT_TOOL_STATUS_LABELS
    return labels.get(tool_name, "Working on your request…")


def tool_status_spoken_filler(tool_name: str) -> str | None:
    meta = _TOOL_STATUS_META.get(tool_name)
    if not meta:
        return None
    spoken = meta.get("spoken")
    return str(spoken) if spoken else None


def tool_status_eta(tool_name: str) -> int | None:
    meta = _TOOL_STATUS_META.get(tool_name)
    if not meta:
        return None
    eta = meta.get("eta_sec")
    return int(eta) if isinstance(eta, int) else None


def _tool_status_from_message(msg: object, *, voice_mode: bool = False) -> str | None:
    """Map an agent tool-call chunk to a human-readable status line."""
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
        if isinstance(name, str):
            return tool_status_label(name, voice_mode=voice_mode)
    chunks = getattr(msg, "tool_call_chunks", None) or []
    for ch in chunks:
        name = ch.get("name") if isinstance(ch, dict) else getattr(ch, "name", None)
        if isinstance(name, str):
            return tool_status_label(name, voice_mode=voice_mode)
    return None


def _tool_name_from_message(msg: object) -> str | None:
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
        if isinstance(name, str):
            return name
    chunks = getattr(msg, "tool_call_chunks", None) or []
    for ch in chunks:
        name = ch.get("name") if isinstance(ch, dict) else getattr(ch, "name", None)
        if isinstance(name, str):
            return name
    return None


def _emit_tool_status(msg: object, *, voice_mode: bool) -> str:
    """Build one SSE status frame for a tool-call message."""
    tool_name = _tool_name_from_message(msg) or ""
    label = _tool_status_from_message(msg, voice_mode=voice_mode) or "Working on your request…"
    return sse_status(
        label,
        spoken_filler=tool_status_spoken_filler(tool_name) if voice_mode else None,
        eta_sec=tool_status_eta(tool_name),
    )


def _friendly_stream_error(exc: Exception) -> str:
    """Turn raw LLM/HTTP exceptions into user-safe chat error text."""
    text = str(exc).strip()
    lower = text.lower()
    if (
        "402" in lower
        or "requires more credits" in lower
        or "can only afford" in lower
        or "openrouter" in lower
        or "error code:" in lower
        or "{'error'" in lower
        or '"error"' in lower
    ):
        return "Failed."
    if "not found" in lower and "conversation" not in lower:
        return "Failed."
    if "401" in lower or "unauthorized" in lower or "invalid api key" in lower:
        return "Failed."
    if "rate limit" in lower or "429" in lower:
        return "Failed."
    return text[:500]


class CreateSessionResponse(BaseModel):
    conversation_id: str
    message: str


class SendMessageRequest(BaseModel):
    content: str
    content_type: str = "text"  # 'text' | 'voice'


async def _persist_assistant_reply(
    settings: Settings,
    conversation_id: str,
    full_response: str,
    title_hint: str,
) -> None:
    """Save the assistant turn on a fresh pooled connection (avoids stale stream conn)."""
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.messages (id, conversation_id, role, content, content_type)
            VALUES ($1::uuid, $2::uuid, 'assistant', $3, 'text')
            """,
            uuid.uuid4(),
            coerce_uuid(conversation_id),
            full_response,
        )
        await conn.execute(
            """
            UPDATE public.conversations
            SET title = CASE WHEN title = 'New conversation' THEN $1 ELSE title END,
                updated_at = NOW()
            WHERE id = $2::uuid
            """,
            title_hint[:60],
            coerce_uuid(conversation_id),
        )


async def _prefetch_top_jobs(
    db: asyncpg.Connection, candidate_id: str, *, limit: int = 5
) -> list[dict]:
    """Load top match cards for voice/chat warmup (reduces first-turn latency)."""
    from hireloop_api.services.job_present import serialize_job_card

    market = await fetch_candidate_market(db, uuid.UUID(candidate_id))
    vis = job_visible_for_market_sql(market_param="$3")
    rows = await db.fetch(
        f"""
        SELECT j.id, j.title, j.location_city, j.location_state,
               j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
               j.employment_type, j.seniority, j.apply_url,
               co.name AS company_name,
               ms.overall_score, ms.explanation
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ms.candidate_id = $1::uuid
          AND j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND (j.expires_at IS NULL OR j.expires_at > NOW())
        ORDER BY ms.overall_score DESC NULLS LAST
        LIMIT $2::integer
        """,
        uuid.UUID(candidate_id),
        limit,
        market,
    )
    return dedupe_jobs([serialize_job_card(dict(r)) for r in rows])


def _job_ingest_search_key(candidate_id: str, search_title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", search_title.lower()).strip("-") or "profile"
    return f"career_path_ingest:{candidate_id}:{slug[:80]}"


async def _enqueue_live_job_ingest_for_search(
    db: asyncpg.Connection,
    *,
    candidate_id: str,
    search_title: str,
    location_city: str | None = None,
) -> None:
    """Queue a live Apify-backed pull for the user's explicit job-search title."""
    from hireloop_api.services.background_jobs import CAREER_PATH_INGEST, enqueue_job

    title = search_title.strip()
    if not title:
        return
    payload: dict[str, object] = {
        "candidate_id": candidate_id,
        "derive_from_candidate": True,
        "requested_titles": [title],
        "force_refresh": True,
    }
    if location_city:
        payload["locations"] = [location_city]
    await enqueue_job(
        db,
        kind=CAREER_PATH_INGEST,
        payload=payload,
        idempotency_key=_job_ingest_search_key(candidate_id, title),
    )


@router.get("/warmup")
async def chat_warmup(
    include_jobs: bool = Query(default=False),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Prefetch profile context before the first chat/voice turn.
    Called on dashboard and /voice mount to hide cold-start latency.
    """
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        coerce_uuid(current_user["id"]),
    )
    if not candidate:
        return {
            "ok": False,
            "profile_completeness": 0,
            "prefetched_jobs": [],
            "match_count": 0,
        }

    candidate_id = str(candidate["id"])
    profile_completeness = await CareerIntelligenceService.get_completeness(db, candidate_id)
    prefetched: list[dict] = []
    match_count = 0
    if include_jobs:
        market = await fetch_candidate_market(db, candidate["id"])
        vis = job_visible_for_market_sql(market_param="$2")
        prefetched = await _prefetch_top_jobs(db, candidate_id, limit=5)
        match_count = int(
            await db.fetchval(
                f"""
                SELECT count(*) FROM public.match_scores ms
                JOIN public.jobs j ON j.id = ms.job_id
                WHERE ms.candidate_id = $1::uuid
                  AND j.is_active = TRUE
                  AND {vis}
                  AND j.deleted_at IS NULL
                """,
                candidate["id"],
                market,
            )
            or 0
        )

    return {
        "ok": True,
        "profile_completeness": profile_completeness,
        "prefetched_jobs": prefetched,
        "match_count": match_count,
    }


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> CreateSessionResponse:
    """Return the candidate's primary Aarya thread (create if this is day one)."""
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        coerce_uuid(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    convo_id = await get_or_create_primary_conversation(
        db,
        user_id=str(current_user["id"]),
        candidate_id=str(candidate["id"]),
    )

    return CreateSessionResponse(
        conversation_id=convo_id,
        message="Conversation ready. Aarya remembers your past chats.",
    )


@router.get("/sessions/primary", response_model=CreateSessionResponse)
async def get_primary_session(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> CreateSessionResponse:
    """Fetch the user's canonical Aarya conversation id (same as POST /sessions)."""
    return await create_session(current_user=current_user, db=db)


@router.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """List all conversations for the current candidate (primary thread first)."""
    rows = await db.fetch(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at, c.is_primary,
               (
                 SELECT count(*) FROM public.messages m
                 WHERE m.conversation_id = c.id
               ) as message_count
        FROM public.conversations c
        JOIN public.candidates ca ON ca.id = c.candidate_id
        WHERE ca.user_id = $1 AND c.deleted_at IS NULL AND c.agent = 'aarya'
        ORDER BY c.is_primary DESC, c.updated_at DESC LIMIT 50
        """,
        coerce_uuid(current_user["id"]),
    )
    return [serialize_row(r) for r in rows]


@router.get("/history")
async def get_user_chat_history(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    Full Aarya chat history for the signed-in user (primary thread, Supabase-backed).
    """
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        coerce_uuid(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    convo_id = await get_or_create_primary_conversation(
        db,
        user_id=str(current_user["id"]),
        candidate_id=str(candidate["id"]),
    )
    rows = await db.fetch(
        """
        SELECT m.id, m.role, m.content, m.content_type, m.audio_url, m.created_at
        FROM public.messages m
        WHERE m.conversation_id = $1::uuid
          AND m.role IN ('user', 'assistant')
        ORDER BY m.created_at ASC
        LIMIT $2 OFFSET $3
        """,
        uuid.UUID(convo_id),
        limit,
        offset,
    )
    total = await db.fetchval(
        """
        SELECT count(*) FROM public.messages m
        WHERE m.conversation_id = $1::uuid
          AND m.role IN ('user', 'assistant')
        """,
        uuid.UUID(convo_id),
    )
    return {
        "conversation_id": convo_id,
        "messages": [serialize_row(r) for r in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


@router.post("/sessions/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """
    Send a message to Aarya and stream the response.
    Uses Server-Sent Events (text/event-stream).
    """
    # #48: every turn is real LLM spend — cap per user per hour.
    check_rate_limit(str(current_user["id"]), "chat_turn", max_per_hour=60)

    pool = await get_db_pool(settings)

    # Pre-stream DB work on a short-lived connection — do not hold through SSE.
    async with pool.acquire() as db:
        # Verify ownership (and grab candidate id for memory persistence)
        convo = await db.fetchrow(
            """
            SELECT c.id, c.candidate_id FROM public.conversations c
            JOIN public.candidates ca ON ca.id = c.candidate_id
            WHERE c.id = $1::uuid AND ca.user_id = $2 AND c.deleted_at IS NULL
            """,
            coerce_uuid(conversation_id),
            coerce_uuid(current_user["id"]),
        )
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")

        candidate_id = str(convo["candidate_id"])
        memory_summary = await CandidateMemoryService.get_memory_summary(db, candidate_id)
        career_facts = await CandidateMemoryService.get_career_facts(db, candidate_id)
        display_name = await resolve_candidate_display_name(
            db,
            user_id=str(current_user["id"]),
            candidate_id=candidate_id,
        )
        known_facts = format_known_facts(
            career_facts,
            canonical_name=display_name,
        )
        open_questions = await CareerIntelligenceService.get_open_questions(db, candidate_id)
        profile_completeness = await CareerIntelligenceService.get_completeness(db, candidate_id)
        prefetched_jobs = await _prefetch_top_jobs(db, candidate_id, limit=5)

        user_msg_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO public.messages (id, conversation_id, role, content, content_type)
            VALUES ($1::uuid, $2::uuid, 'user', $3, $4)
            """,
            user_msg_id,
            coerce_uuid(conversation_id),
            body.content,
            body.content_type,
        )

        career_path_row = await CareerPathService.get_latest(db, candidate_id)
        career_path_prioritized = (career_path_row or {}).get("prioritized_title") or None
        cand_prefs = await db.fetchrow(
            """
            SELECT current_title, looking_for, location_city, location_state
            FROM public.candidates
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
        )
        career_path_pending = (
            career_path_options(career_path_row)
            if career_path_row and not career_path_prioritized
            else []
        )

        last_assistant_row = await db.fetchrow(
            """
            SELECT content FROM public.messages
            WHERE conversation_id = $1::uuid AND role = 'assistant'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            coerce_uuid(conversation_id),
        )
        recent_assistant = last_assistant_row["content"] if last_assistant_row else None

        career_path_just_prioritized = await try_apply_career_path_selection(
            db,
            candidate_id,
            body.content,
            recent_assistant_message=recent_assistant,
        )
        if career_path_just_prioritized:
            career_path_prioritized = career_path_just_prioritized
            career_path_pending = []
            clear_session_tool_cache(conversation_id, "job_search")

        user_intent = _detect_likely_intent(body.content)
        wants_jobs = user_intent == "job_search" or bool(career_path_just_prioritized)
        if wants_jobs:
            ms_count = await db.fetchval(
                """
                SELECT count(*) FROM public.match_scores
                WHERE candidate_id = $1::uuid
                """,
                uuid.UUID(candidate_id),
            )
            if not ms_count:
                try:
                    engine = MatchingEngine(db)
                    await engine.score_candidate(candidate_id, limit=100)
                except Exception as exc:
                    logger.warning(
                        "pre_job_search_scoring_failed",
                        candidate_id=candidate_id,
                        error=str(exc)[:200],
                    )

        search_title = resolve_job_search_query(
            body.content,
            user_intent=user_intent,
            career_path=career_path_row,
            prioritized_title=career_path_prioritized,
            just_prioritized=career_path_just_prioritized,
            current_title=(
                str(cand_prefs["current_title"]).strip()
                if cand_prefs and cand_prefs.get("current_title")
                else None
            ),
            looking_for=(
                str(cand_prefs["looking_for"]).strip()
                if cand_prefs and cand_prefs.get("looking_for")
                else None
            ),
        )
        search_city: str | None = None
        fresh_jobs = wants_fresh_job_results(body.content)
        exclude_job_ids: list[str] = []
        if fresh_jobs:
            clear_session_tool_cache(conversation_id, "job_search")
            exclude_job_ids = await fetch_shown_job_ids(db, conversation_id)
        if search_title is not None:
            _, city = extract_find_role_and_city(body.content)
            search_city = city
            if settings.apify_token:
                try:
                    await _enqueue_live_job_ingest_for_search(
                        db,
                        candidate_id=candidate_id,
                        search_title=search_title,
                        location_city=city,
                    )
                except Exception as exc:
                    logger.warning(
                        "pre_turn_live_job_ingest_enqueue_failed",
                        candidate_id=candidate_id,
                        search_title=search_title,
                        error=str(exc)[:200],
                    )
            try:
                js_kwargs: dict[str, object] = {
                    "query_text": search_title,
                }
                if city:
                    js_kwargs["location_city"] = city
                if exclude_job_ids:
                    js_kwargs["exclude_job_ids"] = exclude_job_ids
                js_result = await aarya_tools.job_search(
                    db,
                    str(current_user["id"]),
                    conversation_id,
                    settings=settings,
                    **js_kwargs,
                )
                if isinstance(js_result, dict) and js_result.get("job_cards"):
                    prefetched_jobs = list(js_result["job_cards"])
            except Exception as exc:
                logger.warning(
                    "pre_turn_job_search_failed",
                    candidate_id=candidate_id,
                    error=str(exc)[:200],
                )

        if wants_jobs and not prefetched_jobs and career_path_row:
            from hireloop_api.services.background_jobs import CAREER_PATH_INGEST, enqueue_job

            ingest_titles = career_path_row.get("target_titles") or []
            if ingest_titles:
                await enqueue_job(
                    db,
                    kind=CAREER_PATH_INGEST,
                    payload={
                        "candidate_id": candidate_id,
                        "derive_from_candidate": True,
                        "force_refresh": True,
                    },
                    idempotency_key=f"career_path_ingest:{candidate_id}",
                )

        # Take the MOST RECENT 50 turns (not the oldest), then restore chronological
        # order. Older context is preserved in the rolling memory summary, so a long
        # conversation never loses its latest turns to the window.
        history = await db.fetch(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at FROM public.messages
                WHERE conversation_id = $1::uuid
                ORDER BY created_at DESC
                LIMIT 50
            ) recent
            ORDER BY created_at ASC
            """,
            coerce_uuid(conversation_id),
        )

    # Long threads: keep only the latest turns in the LLM window. Older context
    # lives in the rolling memory summary loaded above.
    max_history_messages = 12
    if len(history) > max_history_messages:
        history = history[-max_history_messages:]

    include_prefetch = user_intent == "job_search" or bool(career_path_just_prioritized)

    messages = [
        HumanMessage(content=r["content"])
        if r["role"] == "user"
        else AIMessage(content=r["content"])
        for r in history
        if r["role"] in ("user", "assistant")
    ]

    hinglish = _detect_hinglish(body.content)
    initial_state: AaryaState = {
        "messages": messages,
        "user_id": str(current_user["id"]),
        "session_id": conversation_id,
        "action_count": 0,
        "tool_rounds": 0,
        "ui_job_cards": [],
        "voice_mode": body.content_type == "voice",
        "hinglish_detected": hinglish,
        "memory": memory_summary or "",
        "known_facts": known_facts,
        "open_questions": open_questions,
        "profile_completeness": profile_completeness,
        "prefetched_jobs": prefetched_jobs if include_prefetch else [],
        "candidate_display_name": display_name,
        "career_path_prioritized_title": career_path_prioritized,
        "career_path_just_prioritized": career_path_just_prioritized,
        "career_path_pending_options": career_path_pending,
    }

    graph = get_aarya_graph(settings)
    voice_mode = body.content_type == "voice"
    title_hint = body.content[:60]
    deterministic_job_reply: str | None = None
    application_kit_job_ids = (
        _extract_application_kit_job_ids(body.content)
        if user_intent == "job_application"
        else []
    )
    if search_title is not None and user_intent == "job_search":
        location_text = f" in {search_city}" if search_city else ""
        if prefetched_jobs:
            if fresh_jobs:
                deterministic_job_reply = (
                    f"Here are more roles for {search_title or 'your profile'}{location_text} — "
                    "new matches you haven't seen in this chat yet."
                )
            else:
                deterministic_job_reply = (
                    f"I found matching roles for {search_title or 'your profile'}{location_text}. "
                    "I’ve added the best matches below — use Save, Request intro, or Apply on any card."
                )
        else:
            # Only promise a background pull when a path/generic ingest can
            # actually run; otherwise the copy overpromises.
            will_background_ingest = bool(
                settings.apify_token
                and (career_path_row is not None or settings.auto_ingest_on_empty_search)
            )
            if will_background_ingest:
                deterministic_job_reply = (
                    f"I searched for {search_title or 'roles matching your profile'}{location_text}, "
                    "but I couldn’t find live matches yet. "
                    "I’m pulling fresh openings in the background — try again in a minute, "
                    "or widen the role title or location."
                )
            else:
                deterministic_job_reply = (
                    f"I searched for {search_title or 'roles matching your profile'}{location_text}, "
                    "but I couldn’t find live matches yet. "
                    "Try widening the role title or location and I’ll search again."
                )

    logger.info(
        "aarya_turn_start",
        conversation_id=conversation_id,
        channel=body.content_type,
        voice_mode=voice_mode,
    )

    async def event_stream() -> AsyncIterator[str]:
        full_response = ""
        last_msg_id: str | None = None
        try:
            yield sse_status(
                "Thinking… (~3s)…" if voice_mode else "Thinking…",
                spoken_filler="One moment." if voice_mode else None,
                eta_sec=3,
                hinglish_hint=hinglish,
            )
            if include_prefetch and prefetched_jobs:
                yield sse_jobs(prefetched_jobs)
            if application_kit_job_ids:
                yield sse_status(
                    tool_status_label("prepare_application_kit", voice_mode=voice_mode),
                    spoken_filler=(
                        tool_status_spoken_filler("prepare_application_kit")
                        if voice_mode
                        else None
                    ),
                    eta_sec=tool_status_eta("prepare_application_kit"),
                    hinglish_hint=hinglish,
                )
                async with pool.acquire() as db:
                    result = await aarya_tools.prepare_application_kit(
                        db,
                        str(current_user["id"]),
                        conversation_id,
                        settings,
                        job_ids=application_kit_job_ids,
                    )
                full_response = _build_application_kit_reply(result)
                yield sse_text(full_response)
                try:
                    await _persist_assistant_reply(
                        settings, conversation_id, full_response, title_hint
                    )
                except Exception as save_exc:
                    logger.error(
                        "assistant_message_save_failed",
                        error=str(save_exc),
                        conversation_id=conversation_id,
                    )
                yield sse_done()
                return
            if deterministic_job_reply:
                full_response = deterministic_job_reply
                yield sse_text(deterministic_job_reply)
                try:
                    await _persist_assistant_reply(
                        settings, conversation_id, full_response, title_hint
                    )
                except Exception as save_exc:
                    logger.error(
                        "assistant_message_save_failed",
                        error=str(save_exc),
                        conversation_id=conversation_id,
                    )
                yield sse_done()
                return

            async with pool.acquire() as db:
                config = {"configurable": {"db": db, "thread_id": conversation_id}}
                async for mode, chunk in graph.astream(  # type: ignore[misc]
                    initial_state,
                    config=config,
                    stream_mode=["messages", "updates"],
                ):
                    if mode == "updates":
                        for node_name, node_out in chunk.items():
                            if node_name == "agent" and isinstance(node_out, dict):
                                for m in node_out.get("messages", []):
                                    if _tool_status_from_message(m, voice_mode=voice_mode):
                                        yield _emit_tool_status(m, voice_mode=voice_mode)
                            if node_name == "tools" and isinstance(node_out, dict):
                                cards = node_out.get("ui_job_cards") or []
                                if cards:
                                    yield sse_jobs(cards)
                        continue

                    msg, meta = chunk
                    node = meta.get("langgraph_node")
                    if node != "agent":
                        continue

                    if _tool_status_from_message(msg, voice_mode=voice_mode):
                        yield _emit_tool_status(msg, voice_mode=voice_mode)
                        continue

                    if getattr(msg, "tool_calls", None) or getattr(msg, "tool_call_chunks", None):
                        continue
                    content = _agent_message_text(getattr(msg, "content", ""))
                    if content:
                        msg_id = getattr(msg, "id", None)
                        if (
                            last_msg_id is not None
                            and msg_id != last_msg_id
                            and full_response
                            and not full_response.endswith("\n")
                        ):
                            para_break = "\n\n"
                            full_response += para_break
                            yield sse_text(para_break)
                        last_msg_id = msg_id

                        full_response += content
                        yield sse_text(content)

            user_intent = _detect_likely_intent(body.content)
            if user_intent == "profile_improvement" and _looks_incomplete_profile_reply(
                full_response
            ):
                fallback = _build_profile_gap_reply(open_questions)
                prefix = "\n\n" if full_response.strip() else ""
                full_response = (
                    f"{full_response.rstrip()}{prefix}{fallback}"
                    if full_response.strip()
                    else fallback
                )
                yield sse_text(f"{prefix}{fallback}")
                logger.info(
                    "profile_gap_fallback_applied",
                    conversation_id=conversation_id,
                )

            if full_response:
                try:
                    await _persist_assistant_reply(
                        settings, conversation_id, full_response, title_hint
                    )
                except Exception as save_exc:
                    logger.error(
                        "assistant_message_save_failed",
                        error=str(save_exc),
                        conversation_id=conversation_id,
                    )

            yield sse_done()

        except Exception as exc:
            logger.error("aarya_stream_error", error=str(exc), conversation_id=conversation_id)
            if full_response:
                try:
                    await _persist_assistant_reply(
                        settings, conversation_id, full_response, title_hint
                    )
                except Exception as save_exc:
                    logger.error(
                        "assistant_message_save_failed",
                        error=str(save_exc),
                        conversation_id=conversation_id,
                    )
                yield sse_done()
            else:
                err_text = _friendly_stream_error(exc)
                yield sse_error(err_text)
                yield sse_done()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Hireschema-Stream": "aarya-v1",
        },
        # After the reply is fully streamed, remember this exchange: extract
        # profile facts (newer-wins) + refresh the rolling cross-conversation
        # memory. Runs on its own pooled connection and never raises.
        background=BackgroundTask(run_memory_update, settings, candidate_id, conversation_id),
    )


@router.get("/sessions/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get message history for a conversation."""
    rows = await db.fetch(
        """
        SELECT m.id, m.role, m.content, m.content_type, m.audio_url, m.created_at
        FROM public.messages m
        JOIN public.conversations c ON c.id = m.conversation_id
        JOIN public.candidates ca ON ca.id = c.candidate_id
        WHERE m.conversation_id = $1::uuid AND ca.user_id = $2 AND c.deleted_at IS NULL
        ORDER BY m.created_at ASC
        LIMIT $3 OFFSET $4
        """,
        coerce_uuid(conversation_id),
        coerce_uuid(current_user["id"]),
        limit,
        offset,
    )
    return [serialize_row(r) for r in rows]


@router.get("/sessions/{conversation_id}/actions")
async def get_actions(
    conversation_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Get agent action count for the "Aarya performed N actions" UI (R7).
    Also returns a list of recent action types for the activity feed.
    """
    rows = await db.fetch(
        """
        SELECT action_type, created_at, result
        FROM public.agent_actions
        WHERE session_id = $1::uuid AND user_id = $2::uuid AND agent = 'aarya'
        ORDER BY created_at DESC LIMIT 20
        """,
        coerce_uuid(conversation_id),
        coerce_uuid(current_user["id"]),
    )

    # Only surface job cards from job_search in the *current* turn (after the
    # latest user message). Stale searches from earlier turns must not attach.
    last_user_at = await db.fetchval(
        """
        SELECT created_at FROM public.messages
        WHERE conversation_id = $1::uuid AND role = 'user'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        coerce_uuid(conversation_id),
    )

    latest_jobs: list[dict] = []
    latest_application_kits: list[dict] = []
    action_items: list[dict] = []
    for r in rows:
        item: dict = {
            "type": r["action_type"],
            "at": r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat")
            else str(r["created_at"]),
        }
        raw_result = r["result"]
        if isinstance(raw_result, str):
            try:
                raw_result = json.loads(raw_result)
            except (ValueError, TypeError):
                raw_result = None
        action_at = r["created_at"]
        in_current_turn = last_user_at is None or action_at >= last_user_at
        if (
            r["action_type"] == "job_search"
            and in_current_turn
            and isinstance(raw_result, dict)
            and isinstance(raw_result.get("jobs"), list)
            and not latest_jobs
        ):
            latest_jobs = dedupe_jobs(raw_result["jobs"])
            item["jobs"] = latest_jobs
        if (
            r["action_type"] == "prepare_application_kit"
            and in_current_turn
            and isinstance(raw_result, dict)
            and isinstance(raw_result.get("kits"), list)
            and not latest_application_kits
        ):
            latest_application_kits = raw_result["kits"]
            item["application_kits"] = latest_application_kits
        if r["action_type"] == "job_ingest_progress" and isinstance(raw_result, dict):
            item["progress"] = raw_result
        action_items.append(item)

    turn_rows = [r for r in rows if last_user_at is None or r["created_at"] >= last_user_at]

    return {
        "count": len(rows),
        "turn_count": len(turn_rows),
        "actions": action_items,
        "jobs": latest_jobs,
        "application_kits": latest_application_kits,
        "summary": (
            f"Aarya performed {len(turn_rows)} action{'' if len(turn_rows) == 1 else 's'} this turn"
        ),
    }
