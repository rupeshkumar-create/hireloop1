"""
Mock interview routes (P21) — chat-first; voice via same pipeline as P15.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.markets import MARKET_LABELS, currency_for_market, normalize_market
from hireloop_api.services.rate_limit import check_rate_limit

logger = structlog.get_logger()
router = APIRouter(prefix="/mock-interview", tags=["mock-interview"])

MOCK_SYSTEM_BASE = """You are a professional interviewer running a realistic mock interview.

How to run it:
- Ask ONE question at a time, tailored to the target role, seniority, and interview type. Mix
  behavioural (STAR) and role-specific / technical questions.
- After each answer give 2-3 sentences of specific, constructive feedback, then ask the next one.
- Use the candidate's home market context (local salary norms, notice period, companies) where it fits.
  Stay in character.
- Run about 5-6 questions. After the last question's feedback — OR as soon as the candidate says
  they want to stop — WRAP UP.

To wrap up: write a short, warm closing line to the candidate. Then, on a new line, output the
token <end> followed by ONLY a JSON object with EXACTLY these keys (no extra text after it):
{
  "overall_score": <integer 0-10 for overall interview performance>,
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<specific strength>", "..."],
  "areas_to_improve": ["<specific, actionable improvement>", "..."],
  "communication": "<one line on clarity and structure>",
  "technical_accuracy": "<one line on role/technical depth>"
}
Scoring guide: 8-10 strong, 6-7 solid, below 6 needs work. Be honest and encouraging."""


def _mock_system_prompt(market: str) -> str:
    m = normalize_market(market)
    label = MARKET_LABELS.get(m, m)
    currency = currency_for_market(m)
    if m == "IN":
        local = "Use INR/LPA, notice period, and Indian employers where relevant."
    else:
        local = (
            f"Candidate is based in {label}; use {currency} salary framing, not India LPA defaults."
        )
    return f"{MOCK_SYSTEM_BASE}\n{local}"


def _normalize_feedback(raw: Any) -> dict[str, Any]:
    """Coerce the model's end-of-session JSON into the exact shape the UI renders
    (overall_score 0-10, string lists), tolerating scale/format drift."""
    fb: dict[str, Any] = raw if isinstance(raw, dict) else {"summary": str(raw)[:2000]}
    score = fb.get("overall_score")
    if isinstance(score, int | float):
        s = float(score)
        if s > 10:  # model sometimes answers on a 0-100 scale
            s = s / 10.0
        fb["overall_score"] = max(0, min(10, round(s)))

    def _as_list(key: str) -> list[str]:
        v = fb.get(key)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()][:6]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    fb["strengths"] = _as_list("strengths")
    fb["areas_to_improve"] = _as_list("areas_to_improve")
    for key in ("summary", "communication", "technical_accuracy"):
        if key in fb and not isinstance(fb[key], str):
            fb[key] = str(fb[key])
    return fb


class StartMockRequest(BaseModel):
    role_target: str
    interview_type: str = Field(default="recruiter_screen")
    seniority: str | None = None
    mode: str = Field(default="chat", pattern="^(chat|voice)$")


class MockMessageRequest(BaseModel):
    content: str


@router.post("/sessions", status_code=201)
async def start_mock_session(
    body: StartMockRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    # Each mock session drives multiple LLM turns — cap per user per hour.
    await check_rate_limit(str(current_user["id"]), "mock_interview", max_per_hour=10, db=db)

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        current_user["id"],
    )
    if not candidate:
        raise HTTPException(404, "Complete your profile first")

    conv_id = uuid.uuid4()
    mock_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.conversations (id, candidate_id, agent, title)
        VALUES ($1, $2, 'aarya', $3)
        """,
        conv_id,
        candidate["id"],
        f"Mock: {body.role_target}",
    )
    await db.execute(
        """
        INSERT INTO public.mock_interviews (
          id, candidate_id, conversation_id, role_target,
          interview_type, seniority, mode, status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'in_progress')
        """,
        mock_id,
        candidate["id"],
        conv_id,
        body.role_target,
        body.interview_type,
        body.seniority,
        body.mode,
    )
    opening = (
        f"Welcome to your mock {body.interview_type.replace('_', ' ')} for "
        f"{body.role_target}. I'll ask realistic questions — answer as you would in a "
        "real interview. Ready? Here's my first question: Tell me about yourself and "
        "why you're interested in this role."
    )
    await db.execute(
        """
        INSERT INTO public.messages (conversation_id, role, content, content_type)
        VALUES ($1, 'assistant', $2, 'text')
        """,
        conv_id,
        opening,
    )
    return {
        "mock_id": str(mock_id),
        "conversation_id": str(conv_id),
        "opening_message": opening,
    }


@router.get("/sessions/{mock_id}")
async def get_mock_session(
    mock_id: uuid.UUID,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Return session metadata (type, target role, status)."""
    row = await db.fetchrow(
        """
        SELECT mi.id, mi.role_target, mi.interview_type, mi.seniority,
               mi.mode, mi.status, mi.feedback, mi.created_at, mi.completed_at
        FROM public.mock_interviews mi
        JOIN public.candidates c ON c.id = mi.candidate_id
        WHERE mi.id = $1 AND c.user_id = $2
        """,
        mock_id,
        current_user["id"],
    )
    if not row:
        raise HTTPException(404, "Session not found")
    return dict(row)


@router.post("/sessions/{mock_id}/messages")
async def mock_message(
    mock_id: uuid.UUID,
    body: MockMessageRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    row = await db.fetchrow(
        """
        SELECT mi.id, mi.conversation_id, mi.role_target, mi.status,
               mi.seniority, mi.interview_type, mi.job_id, c.id AS candidate_id,
               COALESCE(NULLIF(c.market, ''), NULLIF(u.market, ''), 'IN') AS market
        FROM public.mock_interviews mi
        JOIN public.candidates c ON c.id = mi.candidate_id
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE mi.id = $1 AND c.user_id = $2
        """,
        mock_id,
        current_user["id"],
    )
    if not row or row["status"] != "in_progress":
        raise HTTPException(404, "Session not found or already completed")

    conv_id = row["conversation_id"]
    history = await db.fetch(
        """
        SELECT role, content FROM public.messages
        WHERE conversation_id = $1 ORDER BY created_at ASC
        """,
        conv_id,
    )

    await db.execute(
        """
        INSERT INTO public.messages (conversation_id, role, content, content_type)
        VALUES ($1, 'user', $2, 'text')
        """,
        conv_id,
        body.content,
    )

    llm = ChatOpenAI(
        model=settings.openrouter_primary_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.6,
        max_tokens=1024,
        default_headers={
            "HTTP-Referer": "https://hireschema.com",
            "X-Title": "Hireschema - Mock Interview",
        },
    )
    context_line = f"\nTarget role: {row['role_target']}"
    if row["seniority"]:
        context_line += f"\nSeniority: {row['seniority']}"
    if row["interview_type"]:
        context_line += f"\nInterview type: {str(row['interview_type']).replace('_', ' ')}"
    if row.get("job_id"):
        kit = await db.fetchrow(
            """
            SELECT interview_prep, dossier, cover_letter
            FROM public.job_application_kits
            WHERE candidate_id = $1::uuid AND job_id = $2::uuid
            """,
            row["candidate_id"],
            row["job_id"],
        )
        if kit and kit.get("interview_prep"):
            prep_excerpt = str(kit["interview_prep"])[:2500]
            context_line += (
                f"\n\nUse this application-kit prep (what the candidate submitted):\n{prep_excerpt}"
            )
        if kit and kit.get("cover_letter"):
            context_line += (
                "\n\nCover letter they sent — probe claims from it:\n"
                f"{str(kit['cover_letter'])[:1200]}"
            )
    market = normalize_market(str(row.get("market") or "IN"))
    messages = [SystemMessage(content=_mock_system_prompt(market) + context_line)]
    for h in history[-30:]:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        elif h["role"] == "assistant":
            from langchain_core.messages import AIMessage

            messages.append(AIMessage(content=h["content"]))
    messages.append(HumanMessage(content=body.content))

    resp = await llm.ainvoke(messages)
    reply = resp.content if isinstance(resp.content, str) else str(resp.content)

    feedback = None
    completed = False
    if "<end>" in reply:
        completed = True
        parts = reply.split("<end>", 1)
        reply = parts[0].strip()
        try:
            feedback = _normalize_feedback(json.loads(parts[1].strip()))
        except json.JSONDecodeError:
            feedback = _normalize_feedback(parts[1].strip()[:2000])

    await db.execute(
        """
        INSERT INTO public.messages (conversation_id, role, content, content_type)
        VALUES ($1, 'assistant', $2, 'text')
        """,
        conv_id,
        reply,
    )

    if completed and feedback:
        await db.execute(
            """
            UPDATE public.mock_interviews SET
              status = 'completed',
              feedback = $2::jsonb,
              completed_at = NOW()
            WHERE id = $1
            """,
            mock_id,
            json.dumps(feedback),
        )

    return {"reply": reply, "completed": completed, "feedback": feedback}


@router.get("/sessions")
async def list_mock_sessions(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT mi.id, mi.role_target, mi.interview_type, mi.mode, mi.status,
               mi.confidence_score, mi.created_at, mi.completed_at
        FROM public.mock_interviews mi
        JOIN public.candidates c ON c.id = mi.candidate_id
        WHERE c.user_id = $1
        ORDER BY mi.created_at DESC
        LIMIT 50
        """,
        current_user["id"],
    )
    return [dict(r) for r in rows]
