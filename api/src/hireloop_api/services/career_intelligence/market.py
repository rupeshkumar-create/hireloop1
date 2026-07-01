"""
Live-market grounding for Career Intelligence.

The LLM is good at qualitative inference but should never *invent* market demand
or salary numbers — those are the most decision-critical, most checkable fields
in the whole profile. This module computes them deterministically from the live
Indian ``jobs`` corpus (active, non-expired, country_code='IN') using plain SQL
aggregates, so they carry real evidence and a sample size.

Outputs feed the engine two ways:
  1. ``overlay_market`` writes the grounded numbers onto the profile *after* the
     LLM merge, so facts win over guesses.
  2. ``market_brief`` injects the same numbers into the LLM prompt so the
     qualitative layers (mobility, predictions, gap analysis) stay anchored to
     real demand instead of drifting.

Degrades honestly: below the corpus thresholds (a freshly-seeded or sparse
ingestion) it returns ``grounded=False`` and writes nothing, leaving the LLM's
estimate in place rather than publishing noise from a handful of postings.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog
from pydantic import BaseModel, Field

from hireloop_api.services.career_intelligence.schema import (
    CareerIntelligence,
    SalaryRange,
)

logger = structlog.get_logger()

# Don't ground anything until the corpus is big enough to be meaningful.
_MIN_CORPUS = 8  # total live IN jobs before we trust demand scores
_MIN_COMP_SAMPLE = 5  # postings with a salary band before we trust comp percentiles


# Shared predicate for a "live" posting in the candidate's market.
def _live_sql(market: str, *, job_alias: str = "j") -> str:
    from hireloop_api.markets import job_visible_for_market_sql

    vis = job_visible_for_market_sql(job_alias=job_alias, market_param=f"'{market}'")
    return (
        f"{job_alias}.is_active AND {job_alias}.deleted_at IS NULL AND {vis} "
        f"AND ({job_alias}.expires_at IS NULL OR {job_alias}.expires_at > NOW())"
    )


class MarketFacts(BaseModel):
    """Deterministic, evidence-backed market signals for one candidate."""

    total_live_jobs: int = 0

    grounded_market: bool = False
    skill_demand_score: int | None = None
    role_demand_score: int | None = None
    in_demand_skills: list[str] = Field(default_factory=list)
    top_missing_skills: list[str] = Field(default_factory=list)
    skill_demand_evidence: str | None = None
    role_demand_evidence: str | None = None

    grounded_comp: bool = False
    current_market_value: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    comp_sample_size: int | None = None
    comp_evidence: str | None = None

    role_term: str | None = None


def _candidate_skills(ctx: dict[str, Any]) -> list[str]:
    """Lower-cased, de-duped union of flat skills + resume hard skills."""
    skills: set[str] = set()
    for s in ctx.get("skills") or []:
        text = str(s).strip().lower()
        if text:
            skills.add(text)
    cp = ctx.get("career_profile") or {}
    hard = (cp.get("skills_competencies") or {}).get("hard_skills") or []
    for s in hard:
        name = s.get("skill") or s.get("name") if isinstance(s, dict) else s
        text = str(name or "").strip().lower()
        if text:
            skills.add(text)
    return sorted(skills)


def _role_term(ctx: dict[str, Any]) -> str | None:
    """A title-ish string to match postings against; sanitized for ILIKE."""
    raw = ctx.get("current_title") or ctx.get("looking_for") or ""
    term = str(raw).strip()
    if not term:
        return None
    # Neutralize ILIKE wildcards so a stray % / _ can't widen the match.
    return term.replace("%", "").replace("_", "").strip() or None


async def compute_market_facts(
    db: asyncpg.Connection,
    ctx: dict[str, Any],
) -> MarketFacts:
    """Compute grounded market + compensation signals. Never raises."""
    try:
        return await _compute(db, ctx)
    except Exception as exc:  # grounding is best-effort; never break generation
        logger.warning("career_intelligence_market_grounding_failed", error=str(exc))
        return MarketFacts()


async def _compute(db: asyncpg.Connection, ctx: dict[str, Any]) -> MarketFacts:
    from hireloop_api.markets import normalize_market

    skills = _candidate_skills(ctx)
    role_term = _role_term(ctx)
    facts = MarketFacts(role_term=role_term)
    market = normalize_market(ctx.get("market"))
    live = _live_sql(market)

    total_live = await db.fetchval(f"SELECT count(*) FROM public.jobs j WHERE {live}")
    facts.total_live_jobs = int(total_live or 0)
    if facts.total_live_jobs < _MIN_CORPUS:
        return facts  # corpus too thin to ground anything

    # ── Skill demand: how much of the candidate's skill basket is being hired ──
    if skills:
        matched = await db.fetch(
            f"""
            SELECT lower(s) AS skill, count(*) AS n
            FROM public.jobs j
            CROSS JOIN LATERAL unnest(j.skills_required) AS s
            WHERE {live} AND lower(s) = ANY($1::text[])
            GROUP BY 1
            ORDER BY n DESC
            """,
            skills,
        )
        facts.in_demand_skills = [r["skill"] for r in matched]
        facts.skill_demand_score = round(100 * len(matched) / len(skills))
        facts.skill_demand_evidence = (
            f"{len(matched)} of {len(skills)} skills appear in "
            f"{facts.total_live_jobs} live postings in your market"
        )

        # In-demand skills the candidate is missing, from their own role cluster
        # (postings that share at least one of their skills).
        missing = await db.fetch(
            f"""
            SELECT lower(s) AS skill, count(*) AS n
            FROM public.jobs j
            CROSS JOIN LATERAL unnest(j.skills_required) AS s
            WHERE {live}
              AND EXISTS (
                SELECT 1 FROM unnest(j.skills_required) x
                WHERE lower(x) = ANY($1::text[])
              )
              AND NOT (lower(s) = ANY($1::text[]))
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 10
            """,
            skills,
        )
        facts.top_missing_skills = [r["skill"] for r in missing]

    # ── Role demand: live postings matching the candidate's title ──────────────
    if role_term:
        role_count = await db.fetchval(
            f"SELECT count(*) FROM public.jobs j WHERE {live} AND j.title ILIKE '%' || $1 || '%'",
            role_term,
        )
        role_count = int(role_count or 0)
        facts.role_demand_score = min(100, round(100 * role_count / facts.total_live_jobs))
        facts.role_demand_evidence = (
            f"{role_count} live postings matching '{role_term}' "
            f"of {facts.total_live_jobs} active Indian roles"
        )

    facts.grounded_market = (
        facts.skill_demand_score is not None or facts.role_demand_score is not None
    )

    # ── Compensation: salary-band percentiles from the role cluster ────────────
    comp = await db.fetchrow(
        f"""
        SELECT
          percentile_cont(0.25) WITHIN GROUP (ORDER BY mid) AS p25,
          percentile_cont(0.50) WITHIN GROUP (ORDER BY mid) AS p50,
          percentile_cont(0.75) WITHIN GROUP (ORDER BY mid) AS p75,
          count(*) AS n
        FROM (
          SELECT (COALESCE(j.ctc_min, j.ctc_max) + COALESCE(j.ctc_max, j.ctc_min)) / 2.0 AS mid
          FROM public.jobs j
          WHERE {live}
            AND (j.ctc_min IS NOT NULL OR j.ctc_max IS NOT NULL)
            AND (
              ($1::text[] <> '{{}}'::text[] AND EXISTS (
                SELECT 1 FROM unnest(j.skills_required) x WHERE lower(x) = ANY($1::text[])
              ))
              OR ($2::text IS NOT NULL AND j.title ILIKE '%' || $2 || '%')
            )
        ) t
        """,
        skills,
        role_term,
    )
    comp_n = int((comp and comp["n"]) or 0)
    if comp and comp_n >= _MIN_COMP_SAMPLE and comp["p50"] is not None:
        facts.grounded_comp = True
        facts.current_market_value = round(comp["p50"])
        facts.salary_min = round(comp["p25"]) if comp["p25"] is not None else None
        facts.salary_max = round(comp["p75"]) if comp["p75"] is not None else None
        facts.comp_sample_size = comp_n
        facts.comp_evidence = (
            f"Median of {comp_n} matching live postings with salary bands "
            f"(p25-p75 = {_lpa(facts.salary_min)}-{_lpa(facts.salary_max)})"
        )

    return facts


def _lpa(value: int | None) -> str:
    if value is None:
        return "?"
    return f"{value / 100000:.1f} LPA"


def overlay_market(intel: CareerIntelligence, facts: MarketFacts) -> CareerIntelligence:
    """Write grounded numbers onto the profile — facts win over LLM guesses."""
    if facts.grounded_market:
        intel.market.grounded = True
        intel.market.sample_size = facts.total_live_jobs
        if facts.skill_demand_score is not None:
            intel.market.skill_demand_score = facts.skill_demand_score
        if facts.role_demand_score is not None:
            intel.market.role_demand_score = facts.role_demand_score
        intel.market.skill_demand_evidence = facts.skill_demand_evidence
        intel.market.role_demand_evidence = facts.role_demand_evidence
        intel.market.in_demand_skills = facts.in_demand_skills[:10]
        intel.market.top_missing_skills = facts.top_missing_skills[:10]

    if facts.grounded_comp:
        intel.compensation.grounded = True
        intel.compensation.current_market_value = facts.current_market_value
        intel.compensation.salary_range = SalaryRange(min=facts.salary_min, max=facts.salary_max)
        intel.compensation.sample_size = facts.comp_sample_size
        intel.compensation.evidence = facts.comp_evidence

    return intel


def market_brief(facts: MarketFacts) -> str:
    """A compact evidence block to anchor the LLM's qualitative layers."""
    if not (facts.grounded_market or facts.grounded_comp):
        return ""
    lines = [
        "\nLIVE MARKET EVIDENCE (computed from active Indian job postings — treat "
        "as ground truth; do NOT override these numbers):",
    ]
    if facts.grounded_market:
        if facts.skill_demand_score is not None:
            lines.append(
                f"- Skill demand score: {facts.skill_demand_score} ({facts.skill_demand_evidence})"
            )
        if facts.role_demand_score is not None:
            lines.append(
                f"- Role demand score: {facts.role_demand_score} ({facts.role_demand_evidence})"
            )
        if facts.top_missing_skills:
            lines.append(
                "- In-demand skills this candidate is MISSING (use for "
                f"gap_analysis): {', '.join(facts.top_missing_skills)}"
            )
    if facts.grounded_comp:
        lines.append(
            f"- Market compensation from {facts.comp_sample_size} postings (INR/yr): "
            f"median {facts.current_market_value}, "
            f"range {facts.salary_min}-{facts.salary_max}"
        )
    lines.append(
        "Align the compensation, market, mobility and gap_analysis layers to "
        "this evidence; calibrate predictions to this demand."
    )
    return "\n".join(lines)
