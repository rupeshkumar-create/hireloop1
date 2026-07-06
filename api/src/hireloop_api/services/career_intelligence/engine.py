"""
Career Intelligence engine.

Computes the 24-layer Career Intelligence profile for a candidate from data we
already hold — resume-derived ``career_profile``, Apify ``linkedin_data``, the
flat candidate columns, and the cross-conversation chat ``memory_summary`` — and
persists it to ``candidates.career_intelligence``.

Strategy:
  1. Load everything we know about the candidate.
  2. Seed the hard facts deterministically (name, location, role history,
     total experience) so the model can't hallucinate them.
  3. Run ONE structured LLM pass to infer the scored / predicted layers
     (archetype %, market & compensation estimates, mobility, predictions,
     hidden signals, etc.).
  4. Overlay the deterministic facts on top of the LLM output (facts win),
     validate against the typed schema, compute completeness + open questions,
     and save.

Never raises: on any LLM/parse/DB hiccup it falls back to the deterministic
skeleton so the profile always has *something* to show.
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
from hireloop_api.services.career_intelligence.context import (
    build_source_inventory,
    generate_open_questions,
    overlay_all_sources,
)
from hireloop_api.services.career_intelligence.market import (
    MarketFacts,
    compute_market_facts,
    market_brief,
    overlay_market,
)
from hireloop_api.services.career_intelligence.schema import CareerIntelligence

logger = structlog.get_logger()

_inflight_intelligence_builds: set[str] = set()

_MAX_BRIEF_CHARS = 14000

_ARCHETYPES = (
    "Builder",
    "Operator",
    "Strategist",
    "Innovator",
    "Seller",
    "Leader",
    "Researcher",
    "Creator",
    "Advisor",
)

_SYSTEM_PROMPT = f"""You are a senior career intelligence analyst for an Indian \
recruiting platform. Given everything known about a candidate, produce a rich, \
realistic Career Intelligence profile.

Return ONLY valid JSON (no markdown, no prose). Use this exact shape; omit a \
field only if you genuinely cannot infer it (never invent specific facts like \
employers, dates, or numbers that aren't supported by the input):

{{
  "career_dna": {{
    "archetype_scores": {{"Builder": 0-100, "Operator": 0-100, "Strategist": 0-100,
      "Innovator": 0-100, "Seller": 0-100, "Leader": 0-100, "Researcher": 0-100,
      "Creator": 0-100, "Advisor": 0-100}},
    "primary_archetype": one of {list(_ARCHETYPES)},
    "secondary_archetype": one of {list(_ARCHETYPES)},
    "rationale": "1-2 sentences"
  }},
  "experience": {{"experience_vector": {{"technical_years": float,
    "leadership_years": float, "strategic_years": float, "revenue_years": float,
    "customer_facing_years": float, "operational_years": float}}}},
  "skills": {{"future_skills": ["emerging skills they should learn"],
    "soft_skills": ["inferred soft skills"]}},
  "leadership": {{"leadership_stage":
    "Individual Contributor|Team Lead|Manager|Director|VP|Executive",
    "signals": ["hiring","mentoring",...], "executive_readiness_score": 0-100}},
  "trajectory": {{"promotion_velocity_months": float,
    "growth_path": ["title","->title"], "career_momentum_score": 0-100}},
  "industry": {{"transferability_score": 0-100}},
  "functional": {{"scores": {{"Sales": 0-100, "Marketing": 0-100, "Product": 0-100,
    "Engineering": 0-100, "Operations": 0-100, "Finance": 0-100, "HR": 0-100,
    "Customer Success": 0-100}}}},
  "behavioral": {{"working_style": ["Analytical","Collaborative",...],
    "decision_style": ["Data Driven",...], "risk_appetite": "Low|Medium|High"}},
  "brand": {{"headline_quality": 0-100, "profile_completeness": 0-100,
    "thought_leadership": 0-100, "personal_brand_score": 0-100,
    "influence_score": 0-100}},
  "network": {{"industry_diversity": 0-100, "executive_network_strength": 0-100,
    "hiring_manager_reach": 0-100, "referral_potential_score": 0-100}},
  "market": {{"skill_demand_score": 0-100, "role_demand_score": 0-100,
    "industry_demand_score": 0-100, "automation_risk_score": 0-100,
    "future_proof_score": 0-100, "ai_disruption_risk": 0-100}},
  "compensation": {{"current_market_value": INR_per_annum_int,
    "salary_range": {{"min": int, "max": int}}, "total_compensation": int,
    "equity_potential": "Low|Medium|High", "compensation_growth_potential": 0-100}},
  "mobility": {{
    "adjacent_roles": [{{"role": str, "feasibility_score": 0-100,
      "time_required": "e.g. 6-12 months", "skill_gap": [str]}}],
    "stretch_roles": [same shape], "pivot_roles": [same shape]}},
  "goals": {{"inferred_goals": ["inferred from learning/role changes"]}},
  "risk": {{"job_hopping_risk": 0-100, "skill_obsolescence_risk": 0-100,
    "industry_decline_risk": 0-100, "promotion_stagnation": 0-100,
    "leadership_ceiling": str, "compensation_ceiling": str}},
  "gap_analysis": [{{"target_role": str, "missing_skills": [str],
    "missing_experience": [str], "missing_certifications": [str],
    "missing_leadership_signals": [str], "missing_industry_exposure": [str]}}],
  "prediction": {{
    "most_likely_next_role": {{"outcome": str, "confidence": 0-100}},
    "most_likely_promotion": {{"outcome": str, "confidence": 0-100}},
    "outcome_3_year": {{"outcome": str, "confidence": 0-100}},
    "outcome_5_year": {{"outcome": str, "confidence": 0-100}},
    "outcome_10_year": {{"outcome": str, "confidence": 0-100}}}},
  "path_graph": {{"conservative_path": [str], "accelerated_path": [str],
    "pivot_path": [str], "entrepreneur_path": [str]}},
  "recommendations": {{"jobs": [str], "certifications": [str], "courses": [str],
    "communities": [str], "mentors": [str], "networking_targets": [str],
    "side_projects": [str]}},
  "employability": {{"employability_score": 0-100, "leadership_score": 0-100,
    "technical_score": 0-100, "market_fit_score": 0-100,
    "future_readiness_score": 0-100, "executive_potential_score": 0-100,
    "career_growth_potential_score": 0-100, "career_resilience_score": 0-100}},
  "hidden_signals": {{"ambition_score": 0-100, "adaptability_score": 0-100,
    "influence_score": 0-100, "founder_potential_score": 0-100,
    "executive_potential_score": 0-100}},
  "open_questions": ["specific questions to ask the candidate to fill the
    biggest gaps in this profile (max 8)"]
}}

Rules:
- All scores are integers 0-100. All salary/compensation values are INR per
  annum as integers (e.g. 2500000 for 25 LPA). Calibrate to the Indian market.
- Be specific to THIS person. Job titles and target roles must be real,
  searchable Indian-market titles.
- open_questions should target the most decision-relevant unknowns
  (compensation expectations, goals, preferences, leadership scope)."""


class CareerIntelligenceService:
    """Compute and persist a candidate's Career Intelligence profile."""

    @staticmethod
    async def get(
        db: asyncpg.Connection,
        candidate_id: str,
    ) -> dict[str, Any] | None:
        """Return the stored Career Intelligence dict, or None if not computed."""
        row = await db.fetchrow(
            """
            SELECT career_intelligence, career_intelligence_updated_at
            FROM public.candidates
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
        )
        if not row:
            return None
        ci = _coerce_jsonb(row["career_intelligence"])
        if not ci:
            return None
        updated = row["career_intelligence_updated_at"]
        ci["updated_at"] = updated.isoformat() if isinstance(updated, datetime) else updated
        return ci

    @staticmethod
    async def get_open_questions(
        db: asyncpg.Connection,
        candidate_id: str,
    ) -> list[str]:
        """Return the candidate's outstanding profiling questions.

        Prefers the stored Career Intelligence ``open_questions`` (richer,
        LLM-generated). If intelligence hasn't been computed yet, falls back to a
        cheap deterministic gap list derived from the current profile so Aarya can
        still progressively profile from day one. Never raises.
        """
        try:
            ci = await CareerIntelligenceService.get(db, candidate_id)
            stored = (ci or {}).get("open_questions")
            if isinstance(stored, list) and stored:
                return [str(q) for q in stored if str(q).strip()][:8]

            ctx = await CareerIntelligenceService._load_context(db, candidate_id)
            if ctx is None:
                return []
            return generate_open_questions(_seed_from_context(ctx))
        except Exception as exc:
            logger.warning(
                "career_intelligence_open_questions_failed",
                candidate_id=candidate_id,
                error=str(exc),
            )
            return []

    @staticmethod
    async def get_completeness(
        db: asyncpg.Connection,
        candidate_id: str,
    ) -> int | None:
        """Live profile completeness % — always derived from current DB columns.

        Syncs into stored career_intelligence when stale so the UI pill and Aarya
        stay aligned. Returns None only when the candidate row is missing.
        Never raises.
        """
        try:
            ctx = await CareerIntelligenceService._load_context(db, candidate_id)
            if ctx is None:
                return None
            live = _completeness(ctx)
            stored = await CareerIntelligenceService.get(db, candidate_id)
            stored_val = stored.get("data_completeness") if stored else None
            if stored_val != live:
                await CareerIntelligenceService._sync_completeness(db, candidate_id, live)
            return live
        except Exception:
            return None

    @staticmethod
    async def _sync_completeness(
        db: asyncpg.Connection,
        candidate_id: str,
        pct: int,
    ) -> None:
        """Patch data_completeness on stored CI without a full LLM rebuild."""
        row = await db.fetchrow(
            """
            SELECT career_intelligence
            FROM public.candidates
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
        )
        if not row:
            return
        ci = _coerce_jsonb(row["career_intelligence"]) or {}
        ci["data_completeness"] = pct
        await db.execute(
            """
            UPDATE public.candidates
            SET career_intelligence = $2::jsonb,
                career_intelligence_updated_at = NOW(),
                updated_at = NOW()
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
            json.dumps(ci),
        )

    @staticmethod
    async def generate(
        pool: asyncpg.Pool,
        candidate_id: str,
        settings: Settings,
    ) -> dict[str, Any]:
        """Compute a fresh Career Intelligence profile and persist it.

        Uses short-lived pool connections for DB reads/writes only. The LLM call
        runs without holding a connection — Supabase pooler closes idle conns
        during long OpenRouter requests, which previously caused 500s on save.
        """
        async with pool.acquire() as db:
            ctx = await CareerIntelligenceService._load_context(db, candidate_id)
            if ctx is None:
                raise ValueError("Candidate not found")
            # Ground market + compensation in the live IN jobs corpus before the LLM
            # runs, so the qualitative layers stay anchored to real demand.
            market_facts = await compute_market_facts(db, ctx)

        intel = _seed_from_context(ctx)
        model = settings.openrouter_primary_model

        if settings.openrouter_api_key:
            try:
                llm_data = await CareerIntelligenceService._call_llm(
                    ctx, settings, model, market_facts
                )
            except Exception as exc:  # LLM failures must not break the flow
                logger.warning("career_intelligence_llm_failed", error=str(exc))
                llm_data = None
            if llm_data:
                intel = _merge(intel, llm_data)
            else:
                model = "deterministic"
        else:
            model = "deterministic"

        # Hard facts from resume, LinkedIn, chat, and profile columns always win.
        intel = overlay_all_sources(intel, ctx)
        # Grounded market/comp numbers win over both seed and LLM guesses.
        intel = overlay_market(intel, market_facts)
        intel.model = model
        intel.generated_at = datetime.now(UTC).isoformat()
        intel.data_completeness = _completeness(ctx)
        if not intel.open_questions:
            intel.open_questions = generate_open_questions(intel)

        await CareerIntelligenceService._save(pool, candidate_id, intel)
        return intel.model_dump()

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    async def _load_context(
        db: asyncpg.Connection,
        candidate_id: str,
    ) -> dict[str, Any] | None:
        row = await db.fetchrow(
            """
            SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
                   c.location_city, c.location_state, c.years_experience,
                   c.expected_ctc_min, c.expected_ctc_max, c.current_ctc,
                   c.notice_period_days, c.looking_for, c.skills,
                   c.remote_preference,
                   COALESCE(NULLIF(c.market, ''), u.market, 'IN') AS market,
                   c.career_profile, c.career_analysis, c.linkedin_data, c.aarya_state,
                   c.career_intelligence,
                   u.full_name, u.email
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
        data["career_profile"] = _coerce_jsonb(data.get("career_profile")) or {}
        data["career_analysis"] = _coerce_jsonb(data.get("career_analysis")) or {}
        data["linkedin_data"] = _coerce_jsonb(data.get("linkedin_data")) or {}
        data["aarya_state"] = _coerce_jsonb(data.get("aarya_state")) or {}
        data["career_intelligence"] = _coerce_jsonb(data.get("career_intelligence")) or {}
        resume_row = await db.fetchrow(
            """
            SELECT parsed_data
            FROM public.resumes
            WHERE candidate_id = $1::uuid
            ORDER BY is_primary DESC, version DESC, created_at DESC
            LIMIT 1
            """,
            uuid.UUID(candidate_id),
        )
        resume_exp: list[dict[str, Any]] = []
        if resume_row and resume_row["parsed_data"]:
            parsed = resume_row["parsed_data"]
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except (ValueError, TypeError):
                    parsed = None
            if isinstance(parsed, dict):
                raw_exp = parsed.get("work_experience")
                if isinstance(raw_exp, list):
                    resume_exp = [e for e in raw_exp if isinstance(e, dict)]
        data["resume_work_experience"] = resume_exp
        return data

    @staticmethod
    async def _call_llm(
        ctx: dict[str, Any],
        settings: Settings,
        model: str,
        market_facts: MarketFacts | None = None,
    ) -> dict[str, Any] | None:
        llm = ChatOpenAI(
            model=model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            # The full 24-layer intelligence JSON runs ~5-6k output tokens; 4000
            # truncated it mid-document (finish_reason=length), the parse failed,
            # and the whole thing silently fell back to the deterministic engine
            # (empty Risk factors / Hidden signals). Give it room to finish.
            max_tokens=12000,
            default_headers={
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Career Intelligence",
            },
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_brief(ctx, market_facts)),
        ]
        response = await llm.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        return _parse_json(content)

    @staticmethod
    async def _save(
        pool: asyncpg.Pool,
        candidate_id: str,
        intel: CareerIntelligence,
    ) -> None:
        payload = json.dumps(intel.model_dump())
        cid = uuid.UUID(candidate_id)
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                async with pool.acquire() as db:
                    await db.execute(
                        """
                        UPDATE public.candidates
                        SET career_intelligence = $2::jsonb,
                            career_intelligence_updated_at = NOW(),
                            updated_at = NOW()
                        WHERE id = $1::uuid AND deleted_at IS NULL
                        """,
                        cid,
                        payload,
                    )
                return
            except (
                asyncpg.ConnectionDoesNotExistError,
                asyncpg.InterfaceError,
                ConnectionResetError,
            ) as exc:
                last_exc = exc
                if attempt == 0:
                    logger.warning(
                        "career_intelligence_save_retry",
                        candidate_id=candidate_id,
                        error=str(exc),
                    )
                    continue
                raise
        if last_exc is not None:
            raise last_exc


# ── Background entrypoint ────────────────────────────────────────────────────


async def run_career_intelligence_update(
    settings: Settings,
    candidate_id: str,
    *,
    only_if_missing: bool = False,
) -> None:
    """Fire-and-forget refresh on its own pooled connection. Never raises."""
    from hireloop_api.deps import get_db_pool

    if candidate_id in _inflight_intelligence_builds:
        return
    _inflight_intelligence_builds.add(candidate_id)
    try:
        pool = await get_db_pool(settings)
        if only_if_missing:
            async with pool.acquire() as db:
                existing = await CareerIntelligenceService.get(db, candidate_id)
            if existing:
                return
        # Don't fabricate intelligence from an empty profile. Require at least one
        # real signal (skills, a current title, parsed experience, or a scraped
        # LinkedIn profile) before invoking the LLM — otherwise the output is made
        # up. The candidate populates this via the onboarding LinkedIn-URL/CV step.
        async with pool.acquire() as db:
            has_profile_data = await db.fetchval(
                """
                SELECT
                    COALESCE(array_length(skills, 1), 0) > 0
                    OR NULLIF(TRIM(COALESCE(current_title, '')), '') IS NOT NULL
                    OR (career_profile ? 'experience_career_history')
                    OR (linkedin_data ? 'apify_profile')
                FROM public.candidates
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                candidate_id,
            )
        if not has_profile_data:
            logger.info(
                "career_intelligence_skipped_no_profile_data",
                candidate_id=candidate_id,
            )
            return
        await CareerIntelligenceService.generate(pool, candidate_id, settings)
    except Exception as exc:
        logger.warning(
            "career_intelligence_update_failed",
            candidate_id=candidate_id,
            error=str(exc),
        )
    finally:
        _inflight_intelligence_builds.discard(candidate_id)


async def recompute_completeness_only(
    settings: Settings,
    candidate_id: str,
) -> None:
    """Fast completeness refresh after profile edits — no LLM call. Never raises."""
    from hireloop_api.deps import get_db_pool

    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as db:
            ctx = await CareerIntelligenceService._load_context(db, candidate_id)
            if ctx is None:
                return
            live = _completeness(ctx)
            await CareerIntelligenceService._sync_completeness(db, candidate_id, live)
    except Exception as exc:
        logger.warning(
            "completeness_recompute_failed",
            candidate_id=candidate_id,
            error=str(exc),
        )


# ── Deterministic seeding / facts ────────────────────────────────────────────


def _seed_from_context(ctx: dict[str, Any]) -> CareerIntelligence:
    """Build a baseline profile from hard facts before the LLM enriches it."""
    intel = CareerIntelligence()
    overlay_all_sources(intel, ctx)
    return intel


def _merge(seed: CareerIntelligence, llm_data: dict[str, Any]) -> CareerIntelligence:
    """Validate LLM output and merge it onto the deterministic seed."""
    base = seed.model_dump()
    try:
        # Validate LLM payload through the schema (drops unknown keys / bad types).
        validated = CareerIntelligence.model_validate(llm_data).model_dump()
    except Exception as exc:
        logger.warning("career_intelligence_validation_failed", error=str(exc))
        return seed
    merged = _deep_merge(base, validated, llm_data)
    return CareerIntelligence.model_validate(merged)


def _deep_merge(
    base: dict[str, Any],
    incoming: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    """Merge ``incoming`` onto ``base``, but only where the LLM actually spoke.

    ``raw`` is the unvalidated LLM dict, used to tell "model said null/empty" from
    "model didn't mention this key" — we only override base when the key is
    present in raw with a non-empty value.
    """
    out = dict(base)
    for key, inc_val in incoming.items():
        if key not in raw:
            continue
        base_val = base.get(key)
        raw_val = raw.get(key)
        if isinstance(inc_val, dict) and isinstance(base_val, dict):
            sub_raw = raw_val if isinstance(raw_val, dict) else {}
            out[key] = _deep_merge(base_val, inc_val, sub_raw)
        elif _is_empty(inc_val):
            continue
        else:
            out[key] = inc_val
    return out


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


# ── Completeness + open questions ────────────────────────────────────────────


def _completeness(ctx: dict[str, Any]) -> int:
    """Profile completeness from the candidate's OWN data (weighted, stable).

    Foundation fields (title, skills, experience…) can come from LinkedIn/resume.
    Preference fields (CTC, notice, goals) are weighted separately so one LPA
    answer moves the needle modestly (~10-14%) instead of jumping 60%+ when
    LinkedIn enrichment lands in the same session.
    """
    cp = ctx.get("career_profile") if isinstance(ctx.get("career_profile"), dict) else {}
    exp_hist = cp.get("experience_career_history") if isinstance(cp, dict) else None
    roles = exp_hist.get("roles") if isinstance(exp_hist, dict) else None
    edu_block = cp.get("education_credentials") if isinstance(cp, dict) else None
    education = edu_block.get("education") if isinstance(edu_block, dict) else None
    skills = ctx.get("skills") or []
    headline_or_summary = bool(
        (ctx.get("summary") or "").strip() or (ctx.get("headline") or "").strip()
    )
    remote_pref = ctx.get("remote_preference")
    has_remote = bool(remote_pref and str(remote_pref).strip().lower() not in ("", "unknown"))

    foundation = 0
    if ctx.get("full_name"):
        foundation += 8
    if ctx.get("current_title"):
        foundation += 12
    if ctx.get("current_company"):
        foundation += 10
    if ctx.get("years_experience"):
        foundation += 8
    if ctx.get("location_city"):
        foundation += 8
    if len(skills) >= 3:
        foundation += 12
    if roles:
        foundation += 8
    if education:
        foundation += 6
    if headline_or_summary:
        foundation += 4

    preferences = 0
    if ctx.get("expected_ctc_min") or ctx.get("expected_ctc_max"):
        preferences += 14
    if ctx.get("current_ctc"):
        preferences += 10
    if ctx.get("notice_period_days") is not None:
        preferences += 8
    if ctx.get("looking_for"):
        preferences += 10
    if has_remote:
        preferences += 6

    score = foundation + preferences
    # Without self-reported preferences, cap so LinkedIn import alone can't read 85%+.
    if preferences == 0:
        score = min(score, 62)
    return min(100, score)


# ── Brief builder ────────────────────────────────────────────────────────────


def _build_brief(ctx: dict[str, Any], market_facts: MarketFacts | None = None) -> str:
    cp = ctx.get("career_profile") or {}
    state = ctx.get("aarya_state") or {}
    mem = state.get("memory_summary")
    chat_facts = state.get("career_facts")
    li_blob = ctx.get("linkedin_data") or {}
    li = li_blob.get("apify_profile") or {}
    li_oauth = {
        k: v for k, v in li_blob.items() if k not in ("apify_profile",) and v not in (None, "", {})
    }
    analysis = ctx.get("career_analysis") or {}

    years = ctx.get("years_experience")
    years_str = "unknown" if years is None else str(years)
    notice = ctx.get("notice_period_days")
    notice_str = "unknown" if notice is None else str(notice)
    location = _join_loc(ctx.get("location_city"), ctx.get("location_state")) or "India"
    skills_str = ", ".join(ctx.get("skills") or []) or "not specified"
    ctc_min = ctx.get("expected_ctc_min") or "?"
    ctc_max = ctx.get("expected_ctc_max") or "?"

    parts: list[str] = [
        build_source_inventory(ctx),
        "",
        "CANDIDATE FACTS",
        f"Name: {ctx.get('full_name') or 'Candidate'}",
        f"Current title: {ctx.get('current_title') or 'unknown'}",
        f"Current company: {ctx.get('current_company') or 'unknown'}",
        f"Years experience: {years_str}",
        f"Location: {location}",
        f"Remote preference: {ctx.get('remote_preference') or 'any'}",
        f"Headline: {ctx.get('headline') or '—'}",
        f"Summary: {ctx.get('summary') or '—'}",
        f"Skills: {skills_str}",
        f"Looking for: {ctx.get('looking_for') or '—'}",
        f"Current CTC (INR/yr): {ctx.get('current_ctc') or 'unknown'}",
        f"Expected CTC (INR/yr): {ctc_min} - {ctc_max}",
        f"Notice period (days): {notice_str}",
    ]
    if market_facts is not None:
        evidence = market_brief(market_facts)
        if evidence:
            parts.append(evidence)
    if mem:
        parts.append("\nWHAT WE LEARNED FROM CHAT + VOICE:\n" + str(mem))
    if isinstance(chat_facts, dict) and chat_facts:
        parts.append("\nSTRUCTURED FACTS FROM Q&A (JSON):\n" + _safe_json(chat_facts))
    if cp:
        parts.append("\nRESUME-DERIVED CAREER PROFILE (JSON):\n" + _safe_json(cp))
    if analysis:
        parts.append("\nRESUME CAREER ANALYSIS (JSON):\n" + _safe_json(analysis))
    if li_oauth:
        parts.append("\nLINKEDIN OAUTH / METADATA (JSON):\n" + _safe_json(li_oauth))
    if li:
        parts.append("\nLINKEDIN APIFY PROFILE (JSON):\n" + _safe_json(li))

    brief = "\n".join(parts)
    return brief[:_MAX_BRIEF_CHARS]


def _safe_json(obj: object) -> str:
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


# ── Small helpers ────────────────────────────────────────────────────────────


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
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    # Last resort: the output was truncated (finish_reason=length) so there's no
    # matching close brace. Try to repair it — drop the trailing partial token
    # and close any still-open strings/objects/arrays. Salvages a mostly-complete
    # 24-layer document instead of discarding everything for the deterministic seed.
    if start != -1:
        repaired = _repair_truncated_json(text[start:])
        if repaired is not None:
            return repaired
    return None


def _repair_truncated_json(text: str) -> dict[str, Any] | None:
    """Best-effort close of a JSON object truncated mid-stream."""
    in_string = False
    escaped = False
    last_comma = -1  # last comma outside a string — a clean place to cut
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == ",":
            last_comma = i
    # Cut at the last comma (drop the trailing partial field), then close.
    candidate = text[:last_comma] if last_comma != -1 else text
    # Recompute the open structures for the truncated candidate.
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    if in_string:
        candidate += '"'
    candidate += "".join(reversed(stack))
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _coerce_jsonb(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _join_loc(city: str | None, state: str | None) -> str | None:
    parts = [p for p in (city, state) if p]
    return ", ".join(parts) if parts else None


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None
