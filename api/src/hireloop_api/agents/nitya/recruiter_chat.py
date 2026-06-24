"""
Nitya recruiter intake — fast brief (max 3 recruiter turns).

Separate from NityaIntroHandler (intro handshake worker).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.services.role_jd_extract import suggest_chips_for_reply

logger = structlog.get_logger()

MAX_RECRUITER_TURNS = 3

NITYA_RECRUITER_PROMPT = """\
You are Nitya, Hireloop's AI recruiter partner for hiring managers in India.

The recruiter may have already pasted a JD — structured fields may be pre-filled.
Your job:
1. If JD or brief exists, acknowledge what you extracted (state assumptions clearly).
2. Ask ONLY for gaps that block search: (a) comp structure if unclear, (b) location if missing,
   (c) one must-have if ambiguous. Never ask about all three in one message.
3. Maximum {max_turns} recruiter messages total before you MUST output the brief.
4. Be concise — one short question per turn, no lectures.

Do NOT ask for calibration profiles (bad/borderline/good examples) — skip entirely.

When you have enough (or this is the final turn), output JSON in <brief> tags with keys:
title, jd_structured, evaluation_criteria, hiring_brief, candidate_pitch
(jd_structured may include: seniority, years_experience_min, years_experience_max,
 comp_min_lpa, comp_max_lpa, comp_structure, location_city, location_state, remote_policy,
 must_haves, nice_to_haves)

User-visible text before <brief> should be brief confirmation, not repeat the JSON.
"""


async def ensure_nitya_conversation(
    db: asyncpg.Connection,
    *,
    recruiter_id: uuid.UUID,
    role_id: uuid.UUID,
    title: str,
) -> str:
    """Return Nitya conversation id for a role, creating one if missing (seed/backfill)."""
    conv = await db.fetchrow(
        """
        SELECT id FROM public.conversations
        WHERE role_id = $1 AND agent = 'nitya' AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        role_id,
    )
    if conv:
        return str(conv["id"])

    conv_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.conversations (id, recruiter_id, role_id, agent, title)
        VALUES ($1, $2, $3, 'nitya', $4)
        """,
        conv_id,
        recruiter_id,
        role_id,
        f"Intake: {title}",
    )
    logger.info("nitya_conversation_created", role_id=str(role_id), conversation_id=str(conv_id))
    return str(conv_id)


async def log_nitya_action(
    db: asyncpg.Connection,
    *,
    user_id: str,
    session_id: str,
    action_type: str,
    payload: dict,
    result: dict,
) -> None:
    await db.execute(
        """
        INSERT INTO public.agent_actions (agent, user_id, session_id, action_type, payload, result)
        VALUES ('nitya', $1::uuid, $2::uuid, $3, $4::jsonb, $5::jsonb)
        """,
        user_id,
        session_id,
        action_type,
        json.dumps(payload),
        json.dumps(result),
    )


async def run_nitya_turn(
    db: asyncpg.Connection,
    *,
    llm: ChatOpenAI,
    user_id: str,
    conversation_id: str,
    user_message: str,
    history: list[dict[str, str]],
    role_context: str | None = None,
    recruiter_turn_count: int = 0,
) -> tuple[str, dict[str, Any] | None, list[str]]:
    """
    Single Nitya chat turn. Returns (assistant_text, parsed_brief_or_none, chip_suggestions).
    """
    system = NITYA_RECRUITER_PROMPT.format(max_turns=MAX_RECRUITER_TURNS)
    if role_context:
        system += f"\n\nCurrent role context:\n{role_context}"

    messages = [SystemMessage(content=system)]
    for h in history[-20:]:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))

    final_turn = recruiter_turn_count >= MAX_RECRUITER_TURNS
    user_content = user_message
    if final_turn:
        user_content += (
            "\n\n[SYSTEM: Final recruiter message — output the <brief> JSON now. "
            "Use reasonable assumptions for any missing fields and state them in hiring_brief.]"
        )

    messages.append(HumanMessage(content=user_content))

    await log_nitya_action(
        db,
        user_id=user_id,
        session_id=conversation_id,
        action_type="recruiter_chat_turn",
        payload={"message_preview": user_message[:200], "turn": recruiter_turn_count},
        result={},
    )

    resp = await llm.ainvoke(messages)
    text = resp.content if isinstance(resp.content, str) else str(resp.content)

    brief = None
    if "<brief>" in text and "</brief>" in text:
        raw = text.split("<brief>", 1)[1].split("</brief>", 1)[0].strip()
        try:
            brief = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("nitya_brief_parse_failed")
        text = text.split("<brief>", 1)[0].strip()
    elif final_turn:
        # Force parse attempt if model forgot tags on final turn
        logger.warning("nitya_final_turn_no_brief")

    chips = suggest_chips_for_reply(text) if not brief else []
    return text, brief, chips


NITYA_POST_BRIEF_PROMPT = """\
You are Nitya, Hireloop's AI recruiter partner. The hiring brief is complete.

Help the recruiter in chat:
- Review matched candidates (shown as cards below your message).
- They can request intros or shortlist from the cards — acknowledge when they do.
- If they ask to search again, say you're refreshing matches.
- If they want to publish the role to candidates, mention the Publish action.
- Be concise — one short paragraph max. No bullet lists unless listing 2-3 names by role title.
"""

POST_BRIEF_CHIPS = [
    "Find more candidates",
    "Shortlist the best match",
    "Publish to candidates",
]


def wants_candidate_search(text: str) -> bool:
    t = text.lower()
    return any(
        phrase in t
        for phrase in (
            "find candidate",
            "find more",
            "search again",
            "refresh match",
            "run search",
            "more candidate",
            "new candidate",
        )
    )


def wants_shortlist(text: str) -> bool:
    return "shortlist" in text.lower()


def shortlist_count_from_text(text: str) -> int:
    t = text.lower()
    if "top 3" in t or "three" in t:
        return 3
    if "top 2" in t or "two" in t:
        return 2
    return 1


async def run_nitya_post_brief_turn(
    db: asyncpg.Connection,
    *,
    llm: ChatOpenAI,
    user_id: str,
    conversation_id: str,
    user_message: str,
    history: list[dict[str, str]],
    role_context: str | None = None,
    candidate_count: int = 0,
) -> tuple[str, list[str]]:
    """Post-brief chat turn — no hiring brief JSON."""
    system = NITYA_POST_BRIEF_PROMPT
    if role_context:
        system += f"\n\nRole context:\n{role_context}"
    if candidate_count:
        system += f"\n\n{candidate_count} candidates currently in pipeline."

    messages = [SystemMessage(content=system)]
    for h in history[-20:]:
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        else:
            messages.append(AIMessage(content=h["content"]))
    messages.append(HumanMessage(content=user_message))

    await log_nitya_action(
        db,
        user_id=user_id,
        session_id=conversation_id,
        action_type="recruiter_post_brief_turn",
        payload={"message_preview": user_message[:200]},
        result={},
    )

    resp = await llm.ainvoke(messages)
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    chips = list(POST_BRIEF_CHIPS)
    return text.strip(), chips


async def persist_role_from_brief(
    db: asyncpg.Connection,
    *,
    recruiter_id: uuid.UUID,
    company_id: uuid.UUID,
    role_id: uuid.UUID | None,
    brief: dict[str, Any],
) -> uuid.UUID:
    """Create or update role from parsed brief."""
    title = brief.get("title") or "Untitled Role"
    jd_structured = brief.get("jd_structured") or {}
    if not isinstance(jd_structured, dict):
        jd_structured = {}

    evaluation = brief.get("evaluation_criteria") or []
    hiring_brief = brief.get("hiring_brief") or ""
    pitch = brief.get("candidate_pitch") or ""

    comp_min = jd_structured.get("comp_min_inr")
    comp_max = jd_structured.get("comp_max_inr")
    if comp_min is None and jd_structured.get("comp_min_lpa") is not None:
        comp_min = int(float(jd_structured["comp_min_lpa"]) * 100_000)
    if comp_max is None and jd_structured.get("comp_max_lpa") is not None:
        comp_max = int(float(jd_structured["comp_max_lpa"]) * 100_000)

    location_city = jd_structured.get("location_city")
    location_state = jd_structured.get("location_state")
    remote_policy = jd_structured.get("remote_policy")
    must_haves = jd_structured.get("must_haves") or brief.get("must_haves") or []
    nice_haves = jd_structured.get("nice_to_haves") or brief.get("nice_to_haves") or []

    if role_id:
        row = await db.fetchrow(
            """
            UPDATE public.roles SET
              title = $2,
              jd_structured = $3::jsonb,
              evaluation_criteria = $4::jsonb,
              hiring_brief = $5,
              candidate_pitch = $6,
              calibration_candidates = '[]'::jsonb,
              comp_min = COALESCE($7, comp_min),
              comp_max = COALESCE($8, comp_max),
              location_city = COALESCE($9, location_city),
              location_state = COALESCE($10, location_state),
              remote_policy = COALESCE($11, remote_policy),
              must_haves = COALESCE($12::jsonb, must_haves),
              nice_to_haves = COALESCE($13::jsonb, nice_to_haves),
              version = version + 1,
              updated_at = NOW()
            WHERE id = $1 AND recruiter_id = $14
            RETURNING id, version
            """,
            role_id,
            title,
            json.dumps(jd_structured),
            json.dumps(evaluation),
            hiring_brief,
            pitch,
            comp_min,
            comp_max,
            location_city,
            location_state,
            remote_policy if remote_policy not in ("unknown", None) else None,
            json.dumps(must_haves) if must_haves else None,
            json.dumps(nice_haves) if nice_haves else None,
            recruiter_id,
        )
        if row:
            await db.execute(
                """
                INSERT INTO public.role_versions (role_id, version, snapshot, created_by)
                VALUES ($1, $2, $3::jsonb, NULL)
                ON CONFLICT (role_id, version) DO NOTHING
                """,
                role_id,
                row["version"],
                json.dumps(brief),
            )
        return role_id

    new_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.roles (
          id, company_id, recruiter_id, title, jd_structured,
          evaluation_criteria, hiring_brief, candidate_pitch,
          calibration_candidates, comp_min, comp_max, location_city,
          location_state, remote_policy, must_haves, nice_to_haves, status
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, '[]'::jsonb,
                $9, $10, $11, $12, $13, $14::jsonb, $15::jsonb, 'draft')
        """,
        new_id,
        company_id,
        recruiter_id,
        title,
        json.dumps(jd_structured),
        json.dumps(evaluation),
        hiring_brief,
        pitch,
        comp_min,
        comp_max,
        location_city,
        location_state,
        remote_policy if remote_policy not in ("unknown", None) else None,
        json.dumps(must_haves),
        json.dumps(nice_haves),
    )
    await db.execute(
        """
        INSERT INTO public.role_versions (role_id, version, snapshot)
        VALUES ($1, 1, $2::jsonb)
        """,
        new_id,
        json.dumps(brief),
    )
    return new_id
