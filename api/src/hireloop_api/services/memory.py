"""
Candidate conversation memory + profile extraction.

Aarya should remember what a candidate tells her — not just inside one chat, but
across every conversation — and keep their structured profile in sync with what
they say. This service does both:

  1. Persistent memory: a rolling natural-language summary of everything the
     candidate has shared, stored on candidates.aarya_state and injected into the
     system prompt of every new conversation (see routes/chat.py).
  2. Profile extraction: structured facts mentioned in chat (title, experience,
     skills, CTC, location, notice period, what they're looking for) are written
     back to public.candidates.

Update policy (chosen by the product owner): "update when the candidate says
something newer" — a clear statement in chat refines/overwrites existing profile
fields. Every change is logged (structlog + aarya_state.change_log) so a bad
extraction is auditable and reversible. Skills are merged, never dropped.

Runs as a best-effort background task after each assistant turn — it must never
raise into the chat request.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings
from hireloop_api.deps import get_db_pool
from hireloop_api.services.job_preferences import normalize_remote_preference

logger = structlog.get_logger()

# How many raw messages of the *current* conversation to feed the extractor.
# Older context is preserved in the rolling memory summary, so this stays bounded.
_MAX_MESSAGES = 40

# Hard cap on the rolling memory summary (#46) — it is injected into every
# future system prompt, so it must never grow unbounded. ~200 words.
_MEMORY_SUMMARY_MAX_CHARS = 1500

# Scalar profile fields the extractor may refine. Maps field → ("int" | "str").
_SCALAR_FIELDS: dict[str, str] = {
    "current_title": "str",
    "current_company": "str",
    "years_experience": "int",
    "location_city": "str",
    "location_state": "str",
    "expected_ctc_min": "int",
    "expected_ctc_max": "int",
    "current_ctc": "int",
    "notice_period_days": "int",
    "looking_for": "str",
    "headline": "str",
    "summary": "str",
}

_SYSTEM_PROMPT = """You maintain the profile + memory of a candidate on an Indian \
job platform, based on what they tell Aarya (the AI career assistant) in chat.

You are given: the candidate's current profile, the running memory of past \
conversations, and the latest conversation transcript.

Return ONLY valid JSON (no markdown, no prose) with exactly this shape:
{
  "profile_updates": {
    "current_title": string | null,
    "current_company": string | null,
    "years_experience": integer | null,
    "location_city": string | null,
    "location_state": string | null,
    "expected_ctc_min": integer | null,
    "expected_ctc_max": integer | null,
    "current_ctc": integer | null,
    "notice_period_days": integer | null,
    "looking_for": string | null,
    "headline": string | null,
    "summary": string | null,
    "remote_preference": "any" | "remote_only" | "onsite_only" | null,
    "location_scope": "city" | "state" | "country" | "global" | null,
    "skills_to_add": [string]
  },
  "career_facts": {
    "preferred_name": string | null,
    "relocation_preferences": string | null,
    "work_authorization": string | null,
    "visa_status": string | null,
    "citizenship": string | null,
    "work_mode": "Remote" | "Hybrid" | "Onsite" | null,
    "travel_willingness": string | null,
    "industry_preference": [string],
    "company_size_preference": string | null,
    "startup_vs_enterprise": string | null,
    "desired_title": string | null,
    "desired_industry": string | null,
    "desired_salary": integer | null
  },
  "memory_summary": string
}

Strict rules:
- Only fill a field when the candidate stated it CLEARLY and explicitly in chat. \
If they didn't mention it, use null (for skills_to_add, use []). Never guess.
- All CTC values are INR PER ANNUM as integers (e.g. "25 LPA" → 2500000). \
Convert lakhs/crores correctly. If they gave a monthly figure, annualise it.
- years_experience and notice_period_days are integers.
- looking_for: a short phrase of what role/change they want (e.g. "remote \
backend roles", "switch into product management").
- remote_preference: only when they clearly prefer remote-only or onsite-only \
work; otherwise null. Map "only remote" → remote_only, "must be in office" → \
onsite_only.
- location_scope: how wide a geography they'll take a job in, only when stated. \
Map "only <my city>" → city, "anywhere in <my state>" → state, "anywhere in \
India" / "open to relocating" → country, "open globally"/"anywhere" → global; \
else null.
- skills_to_add: concrete skills/tools they mentioned having (lowercase), \
that aren't obviously already known. Do not invent.
- career_facts: structured identity + preference fields they stated in chat or \
on a voice call. Only fill when explicit; merge newer answers over older ones. \
desired_salary is INR per annum integer. industry_preference is a list of \
industries they want to work in.
- memory_summary: rewrite the running memory into ONE updated third-person \
summary that folds in anything new from this conversation — goals, preferences, \
constraints, companies they like/dislike, family/relocation constraints, \
timeline, anything that helps personalize future chats. Keep it under 200 words. \
Preserve still-relevant older facts; drop nothing important.
"""


class CandidateMemoryService:
    """Extract structured facts + maintain rolling memory from chat."""

    @staticmethod
    async def get_memory_summary(db: asyncpg.Connection, candidate_id: str) -> str | None:
        """Return the candidate's rolling memory summary for prompt injection."""
        row = await db.fetchrow(
            "SELECT aarya_state FROM public.candidates WHERE id = $1::uuid AND deleted_at IS NULL",
            uuid.UUID(candidate_id),
        )
        if not row:
            return None
        state = _coerce_jsonb(row["aarya_state"])
        summary = state.get("memory_summary") if isinstance(state, dict) else None
        return summary if isinstance(summary, str) and summary.strip() else None

    @staticmethod
    async def get_career_facts(db: asyncpg.Connection, candidate_id: str) -> dict[str, Any]:
        """Return the structured career_facts captured from chat/voice (may be empty)."""
        row = await db.fetchrow(
            "SELECT aarya_state FROM public.candidates WHERE id = $1::uuid AND deleted_at IS NULL",
            uuid.UUID(candidate_id),
        )
        if not row:
            return {}
        state = _coerce_jsonb(row["aarya_state"])
        facts = state.get("career_facts") if isinstance(state, dict) else None
        return facts if isinstance(facts, dict) else {}

    @staticmethod
    async def update_from_conversation(
        db: asyncpg.Connection,
        candidate_id: str,
        conversation_id: str,
        settings: Settings,
    ) -> dict[str, Any]:
        """
        Extract facts from the conversation, apply newer-wins profile updates, and
        refresh the rolling memory. Best-effort: logs and returns on any failure.
        """
        if not settings.openrouter_api_key:
            return {"skipped": "no_api_key"}

        profile = await CandidateMemoryService._load_profile(db, candidate_id)
        if profile is None:
            return {"skipped": "no_profile"}

        messages = await CandidateMemoryService._load_messages(db, conversation_id)
        if not messages:
            return {"skipped": "no_messages"}

        prior_summary = await CandidateMemoryService.get_memory_summary(db, candidate_id) or ""

        try:
            parsed = await CandidateMemoryService._call_llm(
                profile, prior_summary, messages, settings
            )
        except Exception as exc:
            logger.warning("memory_extract_llm_failed", error=str(exc))
            return {"skipped": "llm_failed"}

        if not parsed:
            return {"skipped": "no_parse"}

        change_log = await CandidateMemoryService._apply_profile_updates(
            db, candidate_id, profile, parsed.get("profile_updates") or {}
        )
        await CandidateMemoryService._save_memory(
            db, candidate_id, parsed, change_log, conversation_id
        )
        logger.info(
            "memory_updated",
            candidate_id=candidate_id,
            conversation_id=conversation_id,
            fields_changed=[c["field"] for c in change_log],
        )
        return {"changes": change_log}

    # ── internals ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _load_profile(db: asyncpg.Connection, candidate_id: str) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT id, headline, summary, current_title, current_company,
                   location_city, location_state, years_experience,
                   notice_period_days, expected_ctc_min, expected_ctc_max,
                   current_ctc, looking_for, skills, remote_preference, location_scope
            FROM public.candidates
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
        )
        if not row:
            return None
        data = dict(row)
        data["id"] = str(data["id"])
        data["skills"] = list(data.get("skills") or [])
        return data

    @staticmethod
    async def _load_messages(db: asyncpg.Connection, conversation_id: str) -> list[dict[str, str]]:
        rows = await db.fetch(
            """
            SELECT role, content FROM public.messages
            WHERE conversation_id = $1::uuid AND role IN ('user', 'assistant')
            ORDER BY created_at ASC
            LIMIT $2
            """,
            uuid.UUID(conversation_id),
            _MAX_MESSAGES,
        )
        return [{"role": r["role"], "content": r["content"] or ""} for r in rows]

    @staticmethod
    async def _call_llm(
        profile: dict[str, Any],
        prior_summary: str,
        messages: list[dict[str, str]],
        settings: Settings,
    ) -> dict[str, Any] | None:
        # Use the cheaper fallback model — this runs after every turn.
        llm = ChatOpenAI(
            model=settings.openrouter_fallback_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.1,
            max_tokens=1200,
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Aarya Memory",
            },
        )
        brief = _build_brief(profile, prior_summary, messages)
        response = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=brief)]
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        return _parse_json(content)

    @staticmethod
    async def _apply_profile_updates(
        db: asyncpg.Connection,
        candidate_id: str,
        profile: dict[str, Any],
        updates: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Apply newer-wins scalar updates + skill merge. Returns a change log."""
        set_clauses: list[str] = []
        values: list[Any] = []
        change_log: list[dict[str, Any]] = []

        for field, kind in _SCALAR_FIELDS.items():
            new_val = _coerce_scalar(updates.get(field), kind)
            if new_val is None:
                continue
            old_val = profile.get(field)
            if _normalize(old_val) == _normalize(new_val):
                continue
            values.append(new_val)
            set_clauses.append(f"{field} = ${len(values)}")
            change_log.append({"field": field, "old": old_val, "new": new_val})

        raw_remote = updates.get("remote_preference")
        if raw_remote is not None:
            pref = normalize_remote_preference(str(raw_remote))
            if pref != normalize_remote_preference(profile.get("remote_preference")):
                values.append(pref)
                set_clauses.append(f"remote_preference = ${len(values)}")
                change_log.append(
                    {
                        "field": "remote_preference",
                        "old": profile.get("remote_preference"),
                        "new": pref,
                    }
                )

        raw_scope = updates.get("location_scope")
        if raw_scope is not None:
            scope = str(raw_scope).lower().strip()
            if scope in ("city", "state", "country", "global") and scope != profile.get(
                "location_scope"
            ):
                values.append(scope)
                set_clauses.append(f"location_scope = ${len(values)}")
                # Keep the legacy relocation flag coherent with the scope.
                values.append(scope in ("country", "global"))
                set_clauses.append(f"open_to_relocation = ${len(values)}")
                change_log.append(
                    {"field": "location_scope", "old": profile.get("location_scope"), "new": scope}
                )

        # Skills: merge (never drop). Dedup by CANONICAL token so "ReactJS" isn't
        # appended when "react" is already on the profile (alias map in
        # services/skills.py — same canon the matcher uses).
        from hireloop_api.services.skills import canonical_skill

        raw_skills = updates.get("skills_to_add")
        if isinstance(raw_skills, list):
            existing = {canonical_skill(s) for s in (profile.get("skills") or [])}
            additions = [
                str(s).lower().strip()
                for s in raw_skills
                if str(s).strip() and canonical_skill(s) not in existing
            ]
            if additions:
                merged = list(profile.get("skills") or []) + additions
                values.append(merged)
                set_clauses.append(f"skills = ${len(values)}")
                change_log.append({"field": "skills", "added": additions})

        if not set_clauses:
            return []

        values.append(uuid.UUID(candidate_id))
        query = (
            "UPDATE public.candidates SET "  # noqa: S608 - field names are a fixed allowlist
            + ", ".join(set_clauses)
            + ", updated_at = NOW() "
            + f"WHERE id = ${len(values)} AND deleted_at IS NULL"
        )
        await db.execute(query, *values)
        return change_log

    @staticmethod
    async def _save_memory(
        db: asyncpg.Connection,
        candidate_id: str,
        parsed: dict[str, Any],
        change_log: list[dict[str, Any]],
        conversation_id: str,
    ) -> None:
        row = await db.fetchrow(
            "SELECT aarya_state FROM public.candidates WHERE id = $1::uuid",
            uuid.UUID(candidate_id),
        )
        state = _coerce_jsonb(row["aarya_state"]) if row else {}
        if not isinstance(state, dict):
            state = {}

        summary = parsed.get("memory_summary")
        if isinstance(summary, str) and summary.strip():
            # #46: hard budget. The extractor is ASKED for <200 words, but a
            # drifting LLM could grow the summary every turn — and it's injected
            # into every future system prompt, so unbounded growth = unbounded
            # prompt cost. Cap at the word boundary nearest 1500 chars.
            clean = summary.strip()
            if len(clean) > _MEMORY_SUMMARY_MAX_CHARS:
                clean = clean[:_MEMORY_SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "…"
            state["memory_summary"] = clean

        raw_facts = parsed.get("career_facts")
        if isinstance(raw_facts, dict):
            existing_facts = state.get("career_facts")
            if not isinstance(existing_facts, dict):
                existing_facts = {}
            merged_facts = dict(existing_facts)
            for key, val in raw_facts.items():
                if val is None:
                    continue
                if isinstance(val, list) and not val:
                    continue
                if isinstance(val, str) and not val.strip():
                    continue
                merged_facts[key] = val
            if merged_facts:
                state["career_facts"] = merged_facts

        now = datetime.now(UTC).isoformat()
        state["memory_updated_at"] = now
        state["last_conversation_id"] = conversation_id

        if change_log:
            history = state.get("change_log")
            if not isinstance(history, list):
                history = []
            for c in change_log:
                history.append({**c, "at": now, "conversation_id": conversation_id})
            # Keep the log bounded.
            state["change_log"] = history[-50:]

        await db.execute(
            "UPDATE public.candidates SET aarya_state = $1::jsonb, updated_at = NOW() "
            "WHERE id = $2::uuid",
            json.dumps(state),
            uuid.UUID(candidate_id),
        )


# ── Background runner ─────────────────────────────────────────────────────────


async def run_memory_update(settings: Settings, candidate_id: str, conversation_id: str) -> None:
    """
    Fire-and-forget entry point for the chat route. Acquires its own pooled
    connection (the request connection is released by the time this runs) and
    never raises.
    """
    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as conn:
            result = await CandidateMemoryService.update_from_conversation(
                conn, candidate_id, conversation_id, settings
            )
            # If the candidate told us something new (e.g. answered one of Aarya's
            # progressive-profiling questions), recompute Career Intelligence so the
            # scores AND the outstanding open_questions reflect it. Best-effort.
            changes = result.get("changes")

        if changes:
            from hireloop_api.services.career_intelligence import (
                CareerIntelligenceService,
            )
            from hireloop_api.services.career_path import run_career_path_update

            try:
                await CareerIntelligenceService.generate(pool, candidate_id, settings)
            except Exception as ci_exc:
                logger.warning(
                    "career_intelligence_refresh_after_chat_failed",
                    candidate_id=candidate_id,
                    error=str(ci_exc),
                )
            try:
                await run_career_path_update(settings, candidate_id)
            except Exception as path_exc:
                logger.warning(
                    "career_path_refresh_after_chat_failed",
                    candidate_id=candidate_id,
                    error=str(path_exc),
                )
    except Exception as exc:  # best-effort background work
        logger.error("memory_update_failed", error=str(exc), candidate_id=candidate_id)


# ── Module helpers ──────────────────────────────────────────────────────────

# Friendly labels + render order for career_facts when surfaced to Aarya.
_FACT_LABELS: dict[str, str] = {
    "preferred_name": "preferred name",
    "desired_title": "target role",
    "desired_industry": "target industry",
    "desired_salary": "target salary (INR/yr)",
    "work_mode": "work mode",
    "relocation_preferences": "relocation",
    "travel_willingness": "travel",
    "work_authorization": "work authorization",
    "visa_status": "visa status",
    "citizenship": "citizenship",
    "industry_preference": "industries of interest",
    "company_size_preference": "company size",
    "startup_vs_enterprise": "startup vs enterprise",
}


def format_known_facts(facts: dict[str, Any], *, max_chars: int = 600) -> str:
    """
    Render captured career_facts into one compact line for prompt injection, so
    Aarya uses what we already know (preferred name, work mode, target role,
    relocation, etc.) instead of re-asking. Pure + bounded. Empty in → "".
    """
    if not isinstance(facts, dict):
        return ""
    parts: list[str] = []
    for key, label in _FACT_LABELS.items():
        val = facts.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            items = [str(v).strip() for v in val if str(v).strip()]
            if not items:
                continue
            val_str = ", ".join(items)
        else:
            val_str = str(val).strip()
            if not val_str:
                continue
        parts.append(f"{label}: {val_str}")
    return "; ".join(parts)[:max_chars]


def _build_brief(
    profile: dict[str, Any], prior_summary: str, messages: list[dict[str, str]]
) -> str:
    prof_lines = [
        f"current_title: {profile.get('current_title') or '—'}",
        f"current_company: {profile.get('current_company') or '—'}",
        f"years_experience: {profile.get('years_experience')}",
        f"location: {profile.get('location_city') or '—'}, {profile.get('location_state') or '—'}",
        f"expected_ctc_min: {profile.get('expected_ctc_min')}",
        f"expected_ctc_max: {profile.get('expected_ctc_max')}",
        f"current_ctc: {profile.get('current_ctc')}",
        f"notice_period_days: {profile.get('notice_period_days')}",
        f"looking_for: {profile.get('looking_for') or '—'}",
        f"skills: {', '.join(profile.get('skills') or []) or '—'}",
    ]
    convo = "\n".join(
        f"{'Candidate' if m['role'] == 'user' else 'Aarya'}: {m['content']}" for m in messages
    )
    return (
        "CURRENT PROFILE:\n"
        + "\n".join(prof_lines)
        + "\n\nRUNNING MEMORY (from past conversations):\n"
        + (prior_summary or "(none yet)")
        + "\n\nLATEST CONVERSATION:\n"
        + convo
    )


def _parse_json(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _coerce_scalar(value: object, kind: str) -> object | None:
    if value is None:
        return None
    if kind == "int":
        try:
            n = int(float(value))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return None
        return n if n >= 0 else None
    s = str(value).strip()
    return s[:500] if s else None


def _normalize(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _coerce_jsonb(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            obj = json.loads(value)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
