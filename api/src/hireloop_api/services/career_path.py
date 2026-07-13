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
from hireloop_api.markets import MARKET_LABELS, normalize_market

logger = structlog.get_logger()

_inflight_path_builds: set[str] = set()

_SYSTEM_PROMPT_TEMPLATE = """You are Aarya, a career strategist for professionals in {market_label}.

Given a candidate's profile, design a realistic, motivating career path. Be
specific to THIS person — never generic. All roles must be realistic for the
{market_label} job market.

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
- Infer industry from company name, title, location, market, and skills
  (wedding/hospitality, SaaS, retail, manufacturing, healthcare, finance, etc.).
  target_titles MUST stay in the SAME industry and function as their current
  role or the role direction they explicitly selected — never jump to unrelated
  generic titles.
- Hospitality/events/wedding backgrounds → use searchable titles like "Venue Operations
  Manager", "Events Operations Manager", "Wedding Operations Manager" — NOT vague
  "Operations Manager" unless their CV is explicitly general ops outside events.
- The "next" step should be a realistic promotion from their current title at a similar
  company type (e.g. Assistant Manager at a wedding company → "Operations Manager -
  Events" or "Venue Manager", not "Software Operations Manager").
- target_titles are roles they can apply for now or within 12 months — real
  {job_board_phrase}, 3 to 6 items, including their current title or nearest
  equivalent and one natural step up. These strings are sent VERBATIM to Google
  Jobs via Apify — each one MUST be a title people actually post (e.g.
  "Customer Success Manager", "Backend Engineer"). NEVER invent keyword soup,
  skill names, soft skills, or marketing phrases ("Upselling", "Python",
  "Communication skills", "Helping recruiters hire faster").
- Do NOT emit bare generic titles like "Team Lead", "Manager", or "Operations
  Manager" unless the function/domain is included. Use "Implementation Team Lead",
  "Customer Success Team Lead", "CX Operations Manager", "Category Manager", etc.
- Location matters: generate titles that make sense for {market_label}; do not
  use India-only salary, notice-period, or title assumptions for non-IN markets.
- Keep skills_to_build practical and tied to the gaps between steps.
"""


def build_career_path_system_prompt(market: str | None = None) -> str:
    m = normalize_market(market)
    market_label = MARKET_LABELS.get(m, "India")
    board_phrase = "Indian job-board titles"
    return _SYSTEM_PROMPT_TEMPLATE.replace("{market_label}", market_label).replace(
        "{job_board_phrase}", board_phrase
    )


async def expand_similar_titles(
    title: str,
    db: asyncpg.Connection | None = None,
) -> list[str]:
    """Similar, searchable job titles for a preferred career path.

    "Head of Growth" → ["Growth Head", "VP Growth", "Director of Growth", ...]
    so every path casts a realistic net across the synonyms job boards
    actually use. Cached per title (title_expansions) — one LLM call ever per
    distinct title. Best-effort: any failure returns [] and search falls back
    to the title alone.
    """
    from hireloop_api.config import get_settings

    title_norm = " ".join(title.lower().split())
    if db is not None:
        try:
            cached = await db.fetchval(
                "SELECT titles FROM public.title_expansions WHERE title_norm = $1",
                title_norm,
            )
            if cached is not None:
                return list(cached)
        except Exception as exc:
            logger.debug("title_expansion_cache_read_failed", error=str(exc)[:100])

    settings = get_settings()
    if not settings.openrouter_api_key:
        return []

    import httpx

    prompt = (
        "List 4-6 alternative job titles that mean the same role as "
        f'"{title}" on major job boards (India/US/UK). Return ONLY real, '
        "searchable posted titles people hire for (e.g. 'Customer Success "
        "Manager', 'Backend Engineer'). Never skills, keywords, soft skills, "
        "or marketing phrases. Return ONLY a JSON array of strings."
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    # Title expansion is high-volume — use the fast/credit-efficient
                    # model (Gemini Flash by default), not the primary chat model.
                    "model": settings.openrouter_fast_model
                    or settings.openrouter_fallback_model
                    or settings.openrouter_primary_model,
                    "temperature": 0,
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            return []
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", content).strip()
        start, end = content.find("["), content.rfind("]")
        if not (0 <= start < end):
            return []
        parsed = json.loads(content[start : end + 1])
        out: list[str] = []
        for item in parsed:
            t = str(item).strip()
            if t and t.lower() != title.lower():
                out.append(t[:120])
        out = out[:6]
        if db is not None and out:
            try:
                await db.execute(
                    "INSERT INTO public.title_expansions (title_norm, titles) "
                    "VALUES ($1, $2) ON CONFLICT (title_norm) DO NOTHING",
                    title_norm,
                    out,
                )
            except Exception as exc:
                logger.debug("title_expansion_cache_write_failed", error=str(exc)[:100])
        return out
    except Exception as exc:
        logger.warning("title_expansion_failed", error=str(exc)[:150])
        return []


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

        intel_path = path_from_career_intelligence(
            profile,
            profile.get("career_intelligence") or {},
        )
        if intel_path:
            target_locations = _derive_locations(profile)
            async with pool.acquire() as db:
                return await CareerPathService._save(
                    db,
                    candidate_id,
                    intel_path,
                    target_locations,
                    "career_intelligence",
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
            SELECT id, target_titles FROM public.career_paths
            WHERE candidate_id = $1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            uuid.UUID(candidate_id),
        )
        if not row:
            return None

        # Base set: the explicit selection when given, otherwise the path's
        # existing target titles — with the prioritized title always first.
        base: list[str] = []
        seen: set[str] = set()

        def _add(raw: object) -> None:
            t = str(raw or "").strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                base.append(t[:120])

        _add(title)
        for raw in selected_titles or []:
            _add(raw)
        if not selected_titles:
            for raw in list(row["target_titles"] or []):
                _add(raw)
        base = base[:5]

        # EVERY prioritized path gets synonym coverage: expand the preferred
        # title into the titles job boards actually use ("Head of Growth" →
        # "Growth Head", "VP Growth", ...). Cached per title; best-effort.
        seen = {t.lower() for t in base}
        for t in await expand_similar_titles(title, db):
            if t.lower() not in seen:
                seen.add(t.lower())
                base.append(t)
        cleaned_selection = base[:8]

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
                   c.skills, c.career_profile, c.career_intelligence, c.market,
                   u.full_name
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
        raw_intel = data.get("career_intelligence")
        if isinstance(raw_intel, str):
            try:
                raw_intel = json.loads(raw_intel)
            except json.JSONDecodeError:
                raw_intel = {}
        data["career_intelligence"] = raw_intel if isinstance(raw_intel, dict) else {}
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
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Aarya Career Path",
            },
        )
        messages = [
            SystemMessage(content=build_career_path_system_prompt(profile.get("market"))),
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
    market = normalize_market(profile.get("market"))
    city = profile.get("location_city") or "unknown"
    state = profile.get("location_state") or MARKET_LABELS.get(market, "India")
    parts = [
        f"Name: {profile.get('full_name') or 'Candidate'}",
        f"Market: {market}",
        f"Current title: {profile.get('current_title') or 'unknown'}",
        f"Current company: {profile.get('current_company') or 'unknown'}",
        f"Years of experience: {years_str}",
        f"Location: {city}, {state}",
        f"Headline: {profile.get('headline') or '—'}",
        f"Summary: {profile.get('summary') or '—'}",
        f"Skills: {skills}",
    ]
    career_profile = profile.get("career_profile")
    if isinstance(career_profile, dict) and career_profile:
        industries = career_profile.get("industries") or career_profile.get("industry")
        if industries:
            parts.append(f"Industries from CV: {industries}")
        recent_roles = career_profile.get("recent_roles") or career_profile.get("roles")
        if recent_roles:
            parts.append(f"Recent roles from CV: {recent_roles}")
    return "Candidate profile:\n" + "\n".join(parts)


def _infer_industry_bucket(profile: dict[str, Any]) -> str:
    company = (profile.get("current_company") or "").lower()
    title = (profile.get("current_title") or "").lower()
    skills = " ".join(str(s) for s in (profile.get("skills") or [])).lower()
    blob = f"{company} {title} {skills}"
    if any(
        k in blob
        for k in (
            "wedding",
            "event",
            "venue",
            "hospitality",
            "hotel",
            "banquet",
            "catering",
            "resort",
        )
    ):
        return "hospitality_events"
    return "general"


def _fallback_path(profile: dict[str, Any]) -> dict[str, Any]:
    """Deterministic path when the LLM is unavailable or returns junk."""
    title = (profile.get("current_title") or "Professional").strip()
    skills = profile.get("skills") or []
    industry = _infer_industry_bucket(profile)

    if industry == "hospitality_events":
        if "assistant" in title.lower():
            next_title = "Operations Manager - Events"
        elif "manager" in title.lower():
            next_title = "Venue Operations Manager"
        else:
            next_title = f"Senior {title}"
        target_titles = [title, next_title, "Events Operations Manager"]
    else:
        next_title = f"Senior {title}" if not title.lower().startswith("senior") else title
        target_titles = [title, next_title]

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
                "rationale": "A natural next step in your industry, based on your CV.",
                "skills_to_build": [],
            },
        ],
        "target_titles": target_titles,
    }


def path_from_career_intelligence(
    profile: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a kickoff career path from Intelligence mobility.adjacent_roles.

    Keeps chat path picker aligned with the Profile → Intelligence tab.
    Returns None when intelligence has no adjacent roles to use.
    """
    mobility = intelligence.get("mobility")
    if not isinstance(mobility, dict):
        return None
    adjacent_raw = mobility.get("adjacent_roles")
    if not isinstance(adjacent_raw, list) or not adjacent_raw:
        return None

    ranked: list[dict[str, Any]] = []
    for item in adjacent_raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if not role:
            continue
        ranked.append(item)

    if not ranked:
        return None

    ranked.sort(
        key=lambda row: int(row.get("feasibility_score") or 0),
        reverse=True,
    )

    current = (profile.get("current_title") or "Professional").strip()
    skills = list(profile.get("skills") or [])

    steps: list[dict[str, Any]] = [
        {
            "title": current,
            "level": "current",
            "timeframe": "now",
            "rationale": "Where you are today, based on your profile.",
            "skills_to_build": skills[:4],
        }
    ]
    target_titles: list[str] = []
    seen_titles: set[str] = set()

    def _add_title(raw: str) -> None:
        t = raw.strip()
        key = t.lower()
        if t and key not in seen_titles:
            seen_titles.add(key)
            target_titles.append(t)

    for idx, item in enumerate(ranked[:3]):
        role = str(item.get("role")).strip()
        _add_title(role)
        score = item.get("feasibility_score")
        timeframe = str(item.get("time_required") or "").strip() or "6-12 months"
        gaps = item.get("skill_gap") if isinstance(item.get("skill_gap"), list) else []
        gap_labels = [str(g).strip() for g in gaps if str(g).strip()][:3]
        rationale_parts: list[str] = []
        if score is not None:
            rationale_parts.append(f"{int(score)}% fit")
        if gap_labels:
            rationale_parts.append(f"Skills to build: {', '.join(gap_labels)}")
        rationale = (
            " · ".join(rationale_parts)
            if rationale_parts
            else "Adjacent role from your Intelligence profile."
        )
        steps.append(
            {
                "title": role,
                "level": "next" if idx == 0 else "future",
                "timeframe": timeframe,
                "rationale": rationale,
                "skills_to_build": gap_labels,
            }
        )

    for item in ranked[3:6]:
        _add_title(str(item.get("role") or ""))

    top = ranked[0]
    top_role = str(top.get("role")).strip()
    top_score = top.get("feasibility_score")
    prediction = intelligence.get("prediction")
    summary: str | None = None
    if isinstance(prediction, dict):
        likely = prediction.get("most_likely_next_role")
        if isinstance(likely, dict) and likely.get("outcome"):
            summary = str(likely["outcome"]).strip()
    if not summary:
        score_label = f" ({int(top_score)}% fit)" if top_score is not None else ""
        summary = (
            f"Your Intelligence profile ranks {top_role}{score_label} as the strongest "
            "adjacent move, with related paths ordered by feasibility."
        )

    return {
        "current_role": current,
        "summary": summary,
        "steps": steps,
        "target_titles": target_titles,
    }


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


def _looks_like_board_title(title: str) -> bool:
    """Drop LLM inventions that are not usable Google Jobs search queries."""
    t = title.strip()
    if not t or len(t) > 80:
        return False
    words = t.split()
    if len(words) < 1:
        return False
    low = t.lower()
    banned = (
        "upselling",
        "cross-selling",
        "communication skills",
        "soft skills",
        "helping ",
        "passionate",
        "results-driven",
    )
    if any(b in low for b in banned):
        return False
    # Single-token skills/keywords ("python", "sql", "figma") are not job titles.
    if len(words) == 1 and low not in {"founder", "recruiter", "designer", "analyst", "engineer"}:
        roleish = (
            "manager",
            "lead",
            "director",
            "head",
            "engineer",
            "analyst",
            "specialist",
            "executive",
            "associate",
            "officer",
            "designer",
            "recruiter",
            "consultant",
            "founder",
        )
        if low not in roleish and not any(low.endswith(r) for r in roleish):
            return False
    return True


def _clean_titles(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        title = str(item).strip()
        key = title.lower()
        if title and key not in seen and _looks_like_board_title(title):
            seen.add(key)
            out.append(title[:120])
        if len(out) >= 6:
            break
    return out


def _derive_locations(profile: dict[str, Any]) -> list[str]:
    city = (profile.get("location_city") or "").strip()
    return [city] if city else []


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
