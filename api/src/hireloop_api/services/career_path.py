"""
Career path service.

Generates an AI career trajectory for a candidate from their profile, persists
it to public.career_paths, and exposes helpers to read the latest path. The
target role titles produced here drive Apify-backed job discovery (see
routes/career.py).

Flow:
    profile  →  LLM (OpenRouter / Claude)  →  structured path  →  DB row
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings

logger = structlog.get_logger()

_inflight_path_builds: set[str] = set()

_SYSTEM_PROMPT = """You are Aarya, a career strategist for Indian professionals.

Given a candidate's profile, design a realistic, motivating career path. Be
specific to THIS person — never generic. All roles must be realistic for the
Indian job market.

Return ONLY valid JSON (no markdown, no prose) with exactly this shape:
{
  "current_role": "their current role in 2-4 words",
  "summary": "2-3 warm sentences describing where they are and where they can go",
  "steps": [
    {
      "title": "role title",
      "level": "current" | "next" | "future",
      "timeframe": "now" | "6-12 months" | "1-3 years" | "3-5 years",
      "rationale": "one sentence on why this step makes sense for them",
      "skills_to_build": ["skill", "skill"]
    }
  ],
  "target_titles": ["3 to 6 concrete job titles to search for RIGHT NOW"]
}

Rules:
- 3 to 5 steps. The first step's level is "current"; include at least one "next".
- target_titles are the roles they are ready to apply for now or very soon —
  use real, searchable Indian job titles (e.g. "Senior Backend Engineer",
  "Engineering Manager"), not aspirational titles 5 years out.
- Keep skills_to_build practical and tied to the gaps between steps.
"""


class CareerPathService:
    """Generate and persist candidate career paths."""

    @staticmethod
    async def generate(
        pool: asyncpg.Pool,
        candidate_id: str,
        settings: Settings,
    ) -> dict[str, Any]:
        """
        Generate a fresh career path via the LLM and persist it.

        Idempotent under concurrency: parallel calls (double-mounted client
        effects, retries) previously each built and saved a path, and the last
        straggler became get_latest — an UNprioritized row that orphaned the
        candidate's confirmed selection. Now a second caller waits for the
        in-flight build, and a path generated in the last few minutes is
        returned instead of rebuilt.

        Uses short-lived DB connections only for reads/writes; the LLM call runs
        without holding a connection (see career intelligence pattern).
        """
        import asyncio
        from datetime import UTC, timedelta

        def _recent(path: dict[str, Any] | None) -> dict[str, Any] | None:
            if not path or not path.get("created_at"):
                return None
            try:
                created = datetime.fromisoformat(str(path["created_at"]))
            except ValueError:
                return None
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age = datetime.now(UTC) - created
            return path if age < timedelta(minutes=5) else None

        if candidate_id in _inflight_path_builds:
            # Another request is already building — wait for it to land.
            for _ in range(30):
                await asyncio.sleep(2)
                async with pool.acquire() as db:
                    existing = await CareerPathService.get_latest(db, candidate_id)
                recent = _recent(existing)
                if recent is not None:
                    return recent
                if candidate_id not in _inflight_path_builds:
                    break

        async with pool.acquire() as db:
            existing = await CareerPathService.get_latest(db, candidate_id)
        recent = _recent(existing)
        if recent is not None:
            return recent

        _inflight_path_builds.add(candidate_id)
        try:
            return await CareerPathService._generate_fresh(pool, candidate_id, settings)
        finally:
            _inflight_path_builds.discard(candidate_id)

    @staticmethod
    async def _generate_fresh(
        pool: asyncpg.Pool,
        candidate_id: str,
        settings: Settings,
    ) -> dict[str, Any]:
        async with pool.acquire() as db:
            profile = await CareerPathService._load_profile(db, candidate_id)
        if profile is None:
            raise ValueError("Candidate profile not found")

        # Don't fabricate career paths from an empty profile — require a real
        # signal (skills, a current title, or years of experience). The candidate
        # populates this by uploading a CV or adding their LinkedIn URL.
        has_signal = bool(
            (profile.get("skills") or [])
            or (profile.get("current_title") or "").strip()
            or profile.get("years_experience")
        )
        if not has_signal:
            raise ValueError(
                "Add your experience or skills first — there isn't enough yet to map career paths."
            )

        model = settings.openrouter_primary_model
        parsed: dict[str, Any] | None = None

        if settings.openrouter_api_key:
            try:
                parsed = await CareerPathService._call_llm(profile, settings, model)
            except Exception as exc:  # LLM failures must not break the flow
                logger.warning("career_path_llm_failed", error=str(exc))

        if not parsed:
            parsed = _fallback_path(profile)
            model = "fallback"

        target_locations = _derive_locations(profile)
        async with pool.acquire() as db:
            return await CareerPathService._save(db, candidate_id, parsed, target_locations, model)

    @staticmethod
    async def get_latest(
        db: asyncpg.Connection,
        candidate_id: str,
    ) -> dict[str, Any] | None:
        """Return the candidate's most recent (non-deleted) career path, or None."""
        row = await db.fetchrow(
            """
            SELECT id, "current_role", summary, steps, target_titles,
                   target_locations, model, created_at, updated_at, prioritized_title
            FROM public.career_paths
            WHERE candidate_id = $1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            uuid.UUID(candidate_id),
        )
        return _serialize_path(row) if row else None

    @staticmethod
    async def prioritize(
        db: asyncpg.Connection,
        candidate_id: str,
        title: str,
        selected_titles: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Set the prioritized target role on the candidate's latest career path.

        When ``selected_titles`` is given (kickoff multi-select, preferred
        first), it replaces target_titles so downstream job search and path
        resumes are scoped to the candidate's confirmed choices.
        """
        title = title.strip()
        if not title:
            raise ValueError("Title required")
        row = await db.fetchrow(
            """
            SELECT id FROM public.career_paths
            WHERE candidate_id = $1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            uuid.UUID(candidate_id),
        )
        if not row:
            return None

        cleaned_selection: list[str] = []
        if selected_titles:
            seen: set[str] = set()
            for raw in selected_titles:
                t = str(raw).strip()
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    cleaned_selection.append(t[:120])
            cleaned_selection = cleaned_selection[:5]
            # The prioritized title always leads the confirmed set.
            if title.lower() not in {t.lower() for t in cleaned_selection}:
                cleaned_selection.insert(0, title)

        if cleaned_selection:
            updated = await db.fetchrow(
                """
                UPDATE public.career_paths
                SET prioritized_title = $2, target_titles = $3, updated_at = NOW()
                WHERE id = $1
                RETURNING id, "current_role", summary, steps, target_titles,
                          target_locations, model, created_at, updated_at, prioritized_title
                """,
                row["id"],
                title,
                cleaned_selection,
            )
        else:
            updated = await db.fetchrow(
                """
                UPDATE public.career_paths
                SET prioritized_title = $2, updated_at = NOW()
                WHERE id = $1
                RETURNING id, "current_role", summary, steps, target_titles,
                          target_locations, model, created_at, updated_at, prioritized_title
                """,
                row["id"],
                title,
            )
        await db.execute(
            """
            UPDATE public.candidates
            SET looking_for = $2, updated_at = NOW()
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
            title,
        )
        try:
            from hireloop_api.market_db import fetch_candidate_market
            from hireloop_api.services.career_path_pool import link_path_to_definition

            market = await fetch_candidate_market(db, uuid.UUID(candidate_id))
            await link_path_to_definition(db, row["id"], title, market=market)
        except Exception as exc:
            logger.warning("career_path_definition_link_failed", error=str(exc)[:200])
        return _serialize_path(updated) if updated else None

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _load_profile(
        db: asyncpg.Connection,
        candidate_id: str,
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
                   c.location_city, c.location_state, c.years_experience,
                   c.skills, u.full_name
            FROM public.candidates c
            JOIN public.users u ON u.id = c.user_id
            WHERE c.id = $1::uuid AND c.deleted_at IS NULL
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
    async def _call_llm(
        profile: dict[str, Any],
        settings: Settings,
        model: str,
    ) -> dict[str, Any] | None:
        llm = ChatOpenAI(
            model=model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.4,
            max_tokens=1200,
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Aarya Career Path",
            },
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_profile_brief(profile)),
        ]
        response = await llm.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        return _parse_llm_json(content)

    @staticmethod
    async def _save(
        db: asyncpg.Connection,
        candidate_id: str,
        parsed: dict[str, Any],
        target_locations: list[str],
        model: str,
    ) -> dict[str, Any]:
        steps = _clean_steps(parsed.get("steps"))
        target_titles = _clean_titles(parsed.get("target_titles"))
        row = await db.fetchrow(
            """
            INSERT INTO public.career_paths
              (candidate_id, "current_role", summary, steps, target_titles,
               target_locations, model)
            VALUES ($1::uuid, $2, $3, $4::jsonb, $5::text[], $6::text[], $7)
            RETURNING id, "current_role", summary, steps, target_titles,
                      target_locations, model, created_at, updated_at
            """,
            uuid.UUID(candidate_id),
            (parsed.get("current_role") or None),
            (parsed.get("summary") or None),
            json.dumps(steps),
            target_titles,
            target_locations,
            model,
        )
        return _serialize_path(row)


# ── Module helpers ──────────────────────────────────────────────────────────


def _build_profile_brief(profile: dict[str, Any]) -> str:
    skills = ", ".join(profile.get("skills") or []) or "not specified"
    years = profile.get("years_experience")
    years_str = str(years) if years is not None else "unknown"
    city = profile.get("location_city") or "unknown"
    state = profile.get("location_state") or "India"
    parts = [
        f"Name: {profile.get('full_name') or 'Candidate'}",
        f"Current title: {profile.get('current_title') or 'unknown'}",
        f"Current company: {profile.get('current_company') or 'unknown'}",
        f"Years of experience: {years_str}",
        f"Location: {city}, {state}",
        f"Headline: {profile.get('headline') or '—'}",
        f"Summary: {profile.get('summary') or '—'}",
        f"Skills: {skills}",
    ]
    return "Candidate profile:\n" + "\n".join(parts)


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    """Defensively extract a JSON object from an LLM response."""
    if not content:
        return None
    text = content.strip()
    # Strip ```json fences if present.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...last} span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _clean_steps(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    allowed_levels = {"current", "next", "future"}
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        level = str(item.get("level") or "next").strip().lower()
        if level not in allowed_levels:
            level = "next"
        skills = item.get("skills_to_build")
        skills_list = (
            [str(s).strip() for s in skills if str(s).strip()][:6]
            if isinstance(skills, list)
            else []
        )
        cleaned.append(
            {
                "title": title[:120],
                "level": level,
                "timeframe": str(item.get("timeframe") or "").strip()[:40] or None,
                "rationale": str(item.get("rationale") or "").strip()[:280] or None,
                "skills_to_build": skills_list,
            }
        )
    return cleaned


def _clean_titles(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        title = str(item).strip()
        key = title.lower()
        if title and key not in seen:
            seen.add(key)
            out.append(title[:120])
        if len(out) >= 6:
            break
    return out


def _derive_locations(profile: dict[str, Any]) -> list[str]:
    city = (profile.get("location_city") or "").strip()
    return [city] if city else []


def _fallback_path(profile: dict[str, Any]) -> dict[str, Any]:
    """Deterministic path when the LLM is unavailable or returns junk."""
    title = (profile.get("current_title") or "Professional").strip()
    skills = profile.get("skills") or []
    next_title = f"Senior {title}" if not title.lower().startswith("senior") else title
    return {
        "current_role": title,
        "summary": (
            f"You're building strong momentum as a {title}. With focused growth "
            "you can step into more senior, higher-impact roles over the next "
            "couple of years."
        ),
        "steps": [
            {
                "title": title,
                "level": "current",
                "timeframe": "now",
                "rationale": "Where you are today, based on your profile.",
                "skills_to_build": skills[:4],
            },
            {
                "title": next_title,
                "level": "next",
                "timeframe": "6-12 months",
                "rationale": "A natural next step that builds on your current strengths.",
                "skills_to_build": [],
            },
        ],
        "target_titles": [title, next_title],
    }


async def run_career_path_update(
    settings: Settings,
    candidate_id: str,
) -> None:
    """Fire-and-forget career path refresh on its own pooled connection. Never raises."""
    from hireloop_api.deps import get_db_pool

    if candidate_id in _inflight_path_builds:
        return
    _inflight_path_builds.add(candidate_id)
    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as db:
            profile = await CareerPathService._load_profile(db, candidate_id)
        if not profile or not _profile_ready_for_path(profile):
            return
        await CareerPathService.generate(pool, candidate_id, settings)
    except Exception as exc:
        logger.warning(
            "career_path_update_failed",
            candidate_id=candidate_id,
            error=str(exc),
        )
    finally:
        _inflight_path_builds.discard(candidate_id)


def _profile_ready_for_path(profile: dict[str, Any]) -> bool:
    """Minimum signal before we spend an LLM call on a path."""
    if profile.get("current_title"):
        return True
    if profile.get("skills"):
        return True
    headline = str(profile.get("headline") or "").strip()
    return bool(headline and headline.casefold() != "new candidate")


def _serialize_path(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    steps = data.get("steps")
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            steps = []
    created = data.get("created_at")
    updated = data.get("updated_at")
    return {
        "id": str(data["id"]),
        "current_role": data.get("current_role"),
        "summary": data.get("summary"),
        "steps": steps or [],
        "target_titles": list(data.get("target_titles") or []),
        "target_locations": list(data.get("target_locations") or []),
        "model": data.get("model"),
        "prioritized_title": data.get("prioritized_title"),
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
        "updated_at": updated.isoformat() if isinstance(updated, datetime) else updated,
    }
