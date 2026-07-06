"""Public-safe Career Intelligence snapshot for portfolio pages."""

from __future__ import annotations

import json
import re
from typing import Any

_HEADLINE_COMPANY_RE = re.compile(
    r"\s+(?:at|@|·)\s+[^,–—|]+?$",
    re.IGNORECASE,
)


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _top_scores(scores: dict[str, Any] | None, *, limit: int = 5) -> dict[str, int]:
    if not isinstance(scores, dict):
        return {}
    numeric = {str(k): int(v) for k, v in scores.items() if isinstance(v, (int, float))}
    ordered = sorted(numeric.items(), key=lambda kv: kv[1], reverse=True)
    return dict(ordered[:limit])


def _strip_headline_company(headline: str | None) -> str | None:
    if not headline:
        return headline
    stripped = _HEADLINE_COMPANY_RE.sub("", headline.strip())
    return stripped or headline.strip()


def _collect_company_names(
    *,
    current_company: str | None,
    experience: list[dict[str, Any]],
) -> list[str]:
    names: list[str] = []
    if current_company:
        names.append(current_company.strip())
    for row in experience:
        company = row.get("company")
        if isinstance(company, str) and company.strip():
            names.append(company.strip())
    # Longest first so partial replacements don't leave fragments.
    return sorted({n for n in names if n}, key=len, reverse=True)


def _scrub_companies_in_text(text: str | None, companies: list[str]) -> str | None:
    if not text or not companies:
        return text
    out = text
    for name in companies:
        if not name:
            continue
        pattern = re.compile(re.escape(name), re.IGNORECASE)
        out = pattern.sub("a company", out)
    return out


def scrub_profile_for_privacy(
    fields: dict[str, Any],
    experience: list[dict[str, Any]],
    *,
    hide_contact: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Remove employer-identifying strings when contact is hidden."""
    if not hide_contact:
        return fields, experience

    companies = _collect_company_names(
        current_company=fields.get("current_company"),
        experience=experience,
    )
    scrubbed = dict(fields)
    scrubbed["current_company"] = None
    if scrubbed.get("headline"):
        scrubbed["headline"] = _strip_headline_company(str(scrubbed["headline"]))
    if scrubbed.get("summary"):
        scrubbed["summary"] = _scrub_companies_in_text(str(scrubbed["summary"]), companies)

    clean_exp: list[dict[str, Any]] = []
    for row in experience:
        item = dict(row)
        item["company"] = None
        if item.get("description"):
            item["description"] = _scrub_companies_in_text(str(item["description"]), companies)
        clean_exp.append(item)

    return scrubbed, clean_exp


def build_public_intelligence_snapshot(ci_raw: Any) -> dict[str, Any] | None:
    """Trim Career Intelligence to fields safe for anonymous portfolio visitors."""
    ci = _coerce_dict(ci_raw)
    if not ci:
        return None

    dna = _coerce_dict(ci.get("career_dna"))
    employability = _coerce_dict(ci.get("employability"))
    trajectory = _coerce_dict(ci.get("trajectory"))
    market = _coerce_dict(ci.get("market"))
    skills = _coerce_dict(ci.get("skills"))
    achievements = _coerce_dict(ci.get("achievements"))
    leadership = _coerce_dict(ci.get("leadership"))
    learning = _coerce_dict(ci.get("learning"))
    industry = _coerce_dict(ci.get("industry"))
    functional = _coerce_dict(ci.get("functional"))
    behavioral = _coerce_dict(ci.get("behavioral"))
    brand = _coerce_dict(ci.get("brand"))
    mobility = _coerce_dict(ci.get("mobility"))
    goals = _coerce_dict(ci.get("goals"))
    prediction = _coerce_dict(ci.get("prediction"))
    experience = _coerce_dict(ci.get("experience"))
    experience_vector = _coerce_dict(experience.get("experience_vector"))
    identity = _coerce_dict(ci.get("identity"))
    prefs = _coerce_dict(identity.get("career_preferences"))
    explicit_goals = _coerce_dict(goals.get("explicit_goals"))

    next_role = _coerce_dict(prediction.get("most_likely_next_role"))
    highlights = achievements.get("highlights")
    if not isinstance(highlights, list):
        highlights = []

    hard_skills = skills.get("hard_skills")
    if not isinstance(hard_skills, list):
        hard_skills = []

    return {
        "data_completeness": ci.get("data_completeness"),
        "career_dna": {
            "primary_archetype": dna.get("primary_archetype"),
            "secondary_archetype": dna.get("secondary_archetype"),
            "rationale": dna.get("rationale"),
            "archetype_scores": _top_scores(dna.get("archetype_scores")),
        },
        "employability": {
            "overall_score": employability.get("overall_score"),
            "leadership_score": employability.get("leadership_score"),
            "technical_score": employability.get("technical_score"),
            "market_fit_score": employability.get("market_fit_score"),
            "future_readiness_score": employability.get("future_readiness_score"),
            "executive_potential_score": employability.get("executive_potential_score"),
        },
        "trajectory": {
            "career_momentum_score": trajectory.get("career_momentum_score"),
            "growth_path": (trajectory.get("growth_path") or [])[:4]
            if isinstance(trajectory.get("growth_path"), list)
            else [],
            "promotion_velocity_months": trajectory.get("promotion_velocity_months"),
        },
        "prediction": {
            "most_likely_next_role": next_role.get("outcome"),
            "next_role_confidence": next_role.get("confidence"),
            "outcome_3_year": (_coerce_dict(prediction.get("outcome_3_year"))).get("outcome"),
        },
        "market": {
            "skill_demand_score": market.get("skill_demand_score"),
            "role_demand_score": market.get("role_demand_score"),
            "future_proof_score": market.get("future_proof_score"),
            "in_demand_skills": (market.get("in_demand_skills") or [])[:8]
            if isinstance(market.get("in_demand_skills"), list)
            else [],
            "top_missing_skills": (market.get("top_missing_skills") or [])[:6]
            if isinstance(market.get("top_missing_skills"), list)
            else [],
            "grounded": bool(market.get("grounded")),
        },
        "skills": {
            "hard_skills": [
                {
                    "skill": row.get("skill"),
                    "proficiency": row.get("proficiency"),
                    "years": row.get("years"),
                }
                for row in hard_skills[:12]
                if isinstance(row, dict) and row.get("skill")
            ],
            "soft_skills": (skills.get("soft_skills") or [])[:8]
            if isinstance(skills.get("soft_skills"), list)
            else [],
            "future_skills": (skills.get("future_skills") or [])[:6]
            if isinstance(skills.get("future_skills"), list)
            else [],
        },
        "achievements": {
            "highlights": [str(h) for h in highlights[:5] if h],
            "revenue_generated": achievements.get("revenue_generated"),
            "users_acquired": achievements.get("users_acquired"),
            "team_growth": achievements.get("team_growth"),
        },
        "leadership": {
            "leadership_stage": leadership.get("leadership_stage"),
            "executive_readiness_score": leadership.get("executive_readiness_score"),
            "signals": (leadership.get("signals") or [])[:4]
            if isinstance(leadership.get("signals"), list)
            else [],
        },
        "learning": {
            "certifications": (learning.get("certifications") or [])[:6]
            if isinstance(learning.get("certifications"), list)
            else [],
            "learning_velocity": learning.get("learning_velocity"),
        },
        "industry": {
            "industry_exposure": (industry.get("industry_exposure") or [])[:6]
            if isinstance(industry.get("industry_exposure"), list)
            else [],
            "transferability_score": industry.get("transferability_score"),
        },
        "functional": {
            "scores": _top_scores(functional.get("scores"), limit=6),
        },
        "behavioral": {
            "working_style": (behavioral.get("working_style") or [])[:4]
            if isinstance(behavioral.get("working_style"), list)
            else [],
            "risk_appetite": behavioral.get("risk_appetite"),
        },
        "brand": {
            "personal_brand_score": brand.get("personal_brand_score"),
            "profile_completeness": brand.get("profile_completeness"),
        },
        "mobility": {
            "relocation_openness": mobility.get("relocation_openness"),
            "remote_preference": mobility.get("remote_preference"),
        },
        "goals": {
            "desired_title": explicit_goals.get("desired_title"),
            "inferred_goals": (goals.get("inferred_goals") or [])[:4]
            if isinstance(goals.get("inferred_goals"), list)
            else [],
        },
        "experience_vector": {
            "technical_years": experience_vector.get("technical_years"),
            "leadership_years": experience_vector.get("leadership_years"),
            "strategic_years": experience_vector.get("strategic_years"),
            "customer_facing_years": experience_vector.get("customer_facing_years"),
        },
        "preferences": {
            "work_mode": prefs.get("work_mode"),
            "company_size_preference": prefs.get("company_size_preference"),
            "industry_preference": (prefs.get("industry_preference") or [])[:4]
            if isinstance(prefs.get("industry_preference"), list)
            else [],
        },
    }
