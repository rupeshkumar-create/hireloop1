"""
Multi-source context merge for Career Intelligence.

The 24-layer schema is the contract; this module maps *facts* from every input
channel onto those layers before the LLM enriches inferred/scored fields:

  - Resume upload → ``career_profile`` + ``career_analysis`` (6 master groups)
  - LinkedIn OAuth → ``linkedin_data`` (OIDC metadata, profile URL)
  - Apify scrape → ``linkedin_data.apify_profile`` (public profile blob)
  - Chat + voice → ``aarya_state.memory_summary`` + ``aarya_state.career_facts``
  - Profile settings → flat ``candidates`` columns (CTC, looking_for, remote_preference)
  - Live market → ``market.py`` (grounded demand/comp, applied after LLM)

Hard facts from these sources always win over LLM guesses in the engine merge.
"""

from __future__ import annotations

from typing import Any

from hireloop_api.services.career_intelligence.schema import (
    CareerIntelligence,
    GapForRole,
    HardSkill,
    RoleHistoryEntry,
)
from hireloop_api.services.job_preferences import normalize_remote_preference
from hireloop_api.services.profile_experience import (
    _aarya_role_insights,
    build_merged_experience,
    enrich_ctx_from_merged_experience,
    estimate_years_from_experience,
)

_WORK_MODE_LABELS = {
    "any": None,
    "remote_only": "Remote",
    "onsite_only": "Onsite",
}


def overlay_all_sources(intel: CareerIntelligence, ctx: dict[str, Any]) -> CareerIntelligence:
    """Apply deterministic overlays from every available data channel."""
    ctx = enrich_ctx_from_merged_experience(ctx)
    _overlay_columns(intel, ctx)
    _overlay_career_profile(intel, ctx.get("career_profile") or {})
    _overlay_career_analysis(intel, ctx.get("career_analysis") or {})
    _overlay_linkedin(intel, ctx.get("linkedin_data") or {})
    _overlay_chat_facts(intel, ctx)
    _overlay_experience_roles(intel, ctx)
    infer_deterministic_intelligence(intel, ctx)
    return intel


def build_source_inventory(ctx: dict[str, Any]) -> str:
    """Short inventory of which input channels contributed data (for the LLM brief)."""
    lines: list[str] = ["DATA SOURCES AVAILABLE"]
    cp = ctx.get("career_profile") or {}
    li = ctx.get("linkedin_data") or {}
    state = ctx.get("aarya_state") or {}
    mem = state.get("memory_summary")
    facts = state.get("career_facts")

    if cp:
        lines.append("- Resume / CV: career_profile present")
    if ctx.get("career_analysis"):
        lines.append("- Resume / CV: career_analysis present")
    if li.get("apify_profile"):
        lines.append("- LinkedIn: Apify public profile scrape")
    elif li.get("user_metadata") or li.get("oauth_profile_url"):
        lines.append("- LinkedIn: OAuth identity (no Apify scrape yet)")
    if mem:
        lines.append("- Chat + voice: rolling conversation memory")
    if isinstance(facts, dict) and facts:
        lines.append("- Chat + voice: structured career_facts from Q&A")
    if ctx.get("looking_for") or ctx.get("expected_ctc_min"):
        lines.append("- Profile settings: stated goals / compensation")
    if ctx.get("remote_preference") and ctx.get("remote_preference") != "any":
        lines.append("- Profile settings: work location preference")
    if not ctx.get("years_experience") and not cp:
        lines.append("- WARNING: sparse profile — rely on open_questions + chat")
    return "\n".join(lines)


def _overlay_columns(intel: CareerIntelligence, ctx: dict[str, Any]) -> None:
    demo = (ctx.get("career_profile") or {}).get("profile_demographics") or {}

    intel.identity.personal_profile.full_name = ctx.get("full_name") or (
        intel.identity.personal_profile.full_name
    )
    intel.identity.personal_profile.current_location = (
        _join_loc(ctx.get("location_city"), ctx.get("location_state"))
        or intel.identity.personal_profile.current_location
    )
    langs = demo.get("languages_spoken")
    if isinstance(langs, list) and langs:
        intel.identity.personal_profile.languages = [str(x) for x in langs]
    intel.identity.personal_profile.timezone = (
        intel.identity.personal_profile.timezone or "Asia/Kolkata"
    )

    remote_pref = normalize_remote_preference(ctx.get("remote_preference"))
    work_mode = _WORK_MODE_LABELS.get(remote_pref)
    if work_mode and not intel.identity.career_preferences.work_mode:
        intel.identity.career_preferences.work_mode = work_mode

    years = ctx.get("years_experience")
    if years is None:
        exp_hist = (ctx.get("career_profile") or {}).get("experience_career_history") or {}
        years = (exp_hist.get("derived_metrics") or {}).get("total_experience")
    if isinstance(years, int | float):
        intel.experience.total_years = float(years)

    if ctx.get("looking_for"):
        intel.goals.explicit_goals.desired_title = str(ctx["looking_for"])
    if ctx.get("expected_ctc_min") or ctx.get("expected_ctc_max"):
        intel.goals.explicit_goals.desired_salary = ctx.get("expected_ctc_max") or ctx.get(
            "expected_ctc_min"
        )
    if ctx.get("current_ctc") and not intel.compensation.current_market_value:
        intel.compensation.current_market_value = int(ctx["current_ctc"])

    flat_skills = ctx.get("skills") or []
    if isinstance(flat_skills, list) and flat_skills and not intel.skills.hard_skills:
        intel.skills.hard_skills = [_hard_skill(s) for s in flat_skills if str(s).strip()][:40]


def _overlay_career_profile(intel: CareerIntelligence, cp: dict[str, Any]) -> None:
    if not cp:
        return

    demo = cp.get("profile_demographics") or {}
    exp_hist = cp.get("experience_career_history") or {}
    skills_block = cp.get("skills_competencies") or {}
    edu = cp.get("education_credentials") or {}
    achievements = cp.get("achievements_leadership") or {}
    aspirations = cp.get("aspirations_market_fit_recommendations") or {}

    pref_loc = demo.get("preferred_work_location")
    if pref_loc and not intel.identity.personal_profile.relocation_preferences:
        intel.identity.personal_profile.relocation_preferences = str(pref_loc)
    if demo.get("nationality_work_authorization"):
        intel.identity.personal_profile.work_authorization = str(
            demo["nationality_work_authorization"]
        )

    roles = exp_hist.get("roles")
    if isinstance(roles, list) and not intel.experience.role_history:
        intel.experience.role_history = _map_roles(roles)

    derived = exp_hist.get("derived_metrics") or {}
    if derived.get("average_tenure") and not intel.trajectory.promotion_velocity_months:
        avg = derived.get("average_tenure")
        if isinstance(avg, int | float) and avg > 0:
            intel.trajectory.promotion_velocity_months = float(avg)

    progression = (aspirations.get("career_path_recommendation") or {}).get(
        "career_progression_analysis"
    ) or {}
    title_growth = progression.get("title_growth")
    if isinstance(title_growth, list) and title_growth and not intel.trajectory.growth_path:
        intel.trajectory.growth_path = [str(t) for t in title_growth if str(t).strip()]

    hard = skills_block.get("hard_skills") or []
    if isinstance(hard, list) and not intel.skills.hard_skills:
        intel.skills.hard_skills = [_hard_skill(s) for s in hard if str(s).strip()][:40]
    soft = skills_block.get("soft_skills")
    if isinstance(soft, list) and soft and not intel.skills.soft_skills:
        intel.skills.soft_skills = [str(s) for s in soft]
    emerging = skills_block.get("emerging_skills")
    if isinstance(emerging, list) and emerging and not intel.skills.future_skills:
        intel.skills.future_skills = [str(s) for s in emerging]

    impact = achievements.get("achievements_impact") or {}
    if isinstance(impact, dict):
        _copy_if_empty(intel.achievements, "revenue_generated", impact.get("revenue_generated"))
        _copy_if_empty(intel.achievements, "revenue_influenced", impact.get("revenue_influenced"))
        _copy_if_empty(intel.achievements, "pipeline_generated", impact.get("pipeline_generated"))
        _copy_if_empty(intel.achievements, "cost_savings", impact.get("cost_savings"))
        _copy_if_empty(intel.achievements, "team_growth", impact.get("team_growth"))
        _copy_if_empty(intel.achievements, "hiring_impact", impact.get("hiring_impact"))
        highlights = impact.get("highlights") or impact.get("notable_achievements")
        if isinstance(highlights, list) and highlights and not intel.achievements.highlights:
            intel.achievements.highlights = [str(h) for h in highlights][:12]

    leadership = achievements.get("leadership_experience") or {}
    if isinstance(leadership, dict):
        signals: list[str] = []
        if leadership.get("team_management_experience"):
            signals.append("Team management")
        if leadership.get("hiring_experience"):
            signals.append("Hiring")
        if leadership.get("mentoring_experience"):
            signals.append("Mentoring")
        if leadership.get("budget_ownership"):
            signals.append("Budget ownership")
        if leadership.get("cross_functional_leadership"):
            signals.append("Cross-functional leadership")
        if leadership.get("executive_exposure"):
            signals.append("Executive exposure")
        if signals and not intel.leadership.signals:
            intel.leadership.signals = signals

    industry_block = achievements.get("industry_expertise") or {}
    primary = industry_block.get("primary_industry")
    if primary and not intel.industry.industry_exposure:
        intel.industry.industry_exposure = [str(primary)]
    secondary = industry_block.get("secondary_industries")
    if isinstance(secondary, list):
        for ind in secondary:
            if ind and str(ind) not in intel.industry.industry_exposure:
                intel.industry.industry_exposure.append(str(ind))

    certs = edu.get("certifications")
    if isinstance(certs, list) and certs and not intel.learning.certifications:
        intel.learning.certifications = [str(c) for c in certs][:20]

    goals = aspirations.get("career_goals") or {}
    if goals.get("desired_role") and not intel.goals.explicit_goals.desired_title:
        intel.goals.explicit_goals.desired_title = str(goals["desired_role"])
    if goals.get("desired_industry") and not intel.goals.explicit_goals.desired_industry:
        intel.goals.explicit_goals.desired_industry = str(goals["desired_industry"])

    interests = aspirations.get("career_interests")
    if isinstance(interests, list) and interests and not intel.goals.inferred_goals:
        intel.goals.inferred_goals = [str(i) for i in interests][:8]

    gap_list = (aspirations.get("career_path_recommendation") or {}).get("gap_analysis")
    if isinstance(gap_list, list) and gap_list and not intel.gap_analysis:
        for gap in gap_list[:5]:
            if not isinstance(gap, dict):
                continue
            target = gap.get("target_role") or gap.get("role")
            if not target:
                continue
            intel.gap_analysis.append(
                GapForRole(
                    target_role=str(target),
                    missing_skills=[str(s) for s in (gap.get("missing_skills") or [])],
                    missing_experience=[str(s) for s in (gap.get("missing_experience") or [])],
                )
            )


def _overlay_career_analysis(intel: CareerIntelligence, analysis: dict[str, Any]) -> None:
    if not analysis:
        return
    dna = analysis.get("career_dna") or analysis.get("archetype")
    if isinstance(dna, dict):
        scores = dna.get("archetype_scores") or dna.get("scores")
        if isinstance(scores, dict) and scores and not intel.career_dna.archetype_scores:
            intel.career_dna.archetype_scores = {
                str(k): int(v) for k, v in scores.items() if isinstance(v, int | float)
            }
        if dna.get("primary_archetype"):
            intel.career_dna.primary_archetype = str(dna["primary_archetype"])
        if dna.get("secondary_archetype"):
            intel.career_dna.secondary_archetype = str(dna["secondary_archetype"])

    employability = analysis.get("employability") or analysis.get("market_readiness")
    if isinstance(employability, dict):
        for field, attr in (
            ("employability_score", "employability_score"),
            ("leadership_score", "leadership_score"),
            ("technical_score", "technical_score"),
            ("market_fit_score", "market_fit_score"),
        ):
            val = employability.get(field)
            if isinstance(val, int | float) and getattr(intel.employability, attr) is None:
                setattr(intel.employability, attr, int(val))


def _overlay_linkedin(intel: CareerIntelligence, linkedin_data: dict[str, Any]) -> None:
    if not linkedin_data:
        return

    apify = linkedin_data.get("apify_profile") or {}
    oauth_meta = linkedin_data.get("user_metadata") or {}

    if oauth_meta.get("name") and not intel.identity.personal_profile.full_name:
        intel.identity.personal_profile.full_name = str(oauth_meta["name"])

    li_name = apify.get("name") or apify.get("fullName")
    if li_name and not intel.identity.personal_profile.full_name:
        intel.identity.personal_profile.full_name = str(li_name)

    headline = apify.get("headline")
    if headline and intel.brand.headline_quality is None:
        intel.brand.headline_quality = min(100, 40 + min(len(str(headline)), 120) // 2)

    summary = apify.get("summary")
    if summary and intel.brand.profile_completeness is None:
        intel.brand.profile_completeness = min(100, 30 + min(len(str(summary)), 800) // 10)

    conns = apify.get("connectionsCount") or apify.get("connections")
    if isinstance(conns, int):
        intel.network.connections = conns
    followers = apify.get("followersCount") or apify.get("followers")
    if isinstance(followers, int):
        intel.network.followers = followers

    li_skills = apify.get("skills")
    if isinstance(li_skills, list) and li_skills:
        existing = {s.skill.casefold() for s in intel.skills.hard_skills}
        for skill in li_skills[:30]:
            name = str(skill).strip()
            if name and name.casefold() not in existing:
                intel.skills.hard_skills.append(HardSkill(skill=name, recency="LinkedIn"))
                existing.add(name.casefold())

    positions = apify.get("currentPositions") or apify.get("positions") or apify.get("experiences")
    if isinstance(positions, list) and positions and not intel.experience.role_history:
        intel.experience.role_history = _map_linkedin_positions(positions)


def _overlay_experience_roles(intel: CareerIntelligence, ctx: dict[str, Any]) -> None:
    """Rich role history from LinkedIn + resume + career_profile, with Aarya bullets."""
    merged = ctx.get("_merged_experience")
    if merged is None:
        merged = build_merged_experience(
            resume_experience=ctx.get("resume_work_experience"),
            linkedin_data=ctx.get("linkedin_data"),
            career_profile=ctx.get("career_profile"),
            career_intelligence=ctx.get("career_intelligence"),
            candidate={
                "current_title": ctx.get("current_title"),
                "current_company": ctx.get("current_company"),
            },
            skills=ctx.get("skills"),
        )

    if merged:
        skills = [str(s) for s in (ctx.get("skills") or [])]
        intel.experience.role_history = [
            RoleHistoryEntry(
                title=_str_or_none(m.get("title")),
                industry=_str_or_none(m.get("industry")),
                seniority=_str_or_none(m.get("seniority")),
                function=_str_or_none(m.get("employment_type")),
                aarya_insights=list(m.get("aarya_insights") or _aarya_role_insights(m, skills))[:5],
            )
            for m in merged[:15]
        ]
        if not intel.experience.total_years:
            years = estimate_years_from_experience(
                merged,
                fallback=ctx.get("years_experience"),
            )
            if years:
                intel.experience.total_years = years
        return

    if intel.experience.role_history:
        skills = [str(s) for s in (ctx.get("skills") or [])]
        for entry in intel.experience.role_history:
            if entry.aarya_insights:
                continue
            role_dict = entry.model_dump()
            entry.aarya_insights = _aarya_role_insights(role_dict, skills)


def infer_deterministic_intelligence(intel: CareerIntelligence, ctx: dict[str, Any]) -> None:
    """Seed scored layers from facts when the LLM hasn't filled them yet."""
    title = (ctx.get("current_title") or ctx.get("looking_for") or "").casefold()
    skills = [str(s).casefold() for s in (ctx.get("skills") or [])]
    years = intel.experience.total_years or ctx.get("years_experience") or 0
    role_count = len(intel.experience.role_history)

    if not intel.career_dna.archetype_scores:
        scores = _heuristic_archetype_scores(title, skills)
        intel.career_dna.archetype_scores = scores
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if ranked:
            intel.career_dna.primary_archetype = ranked[0][0]
            if len(ranked) > 1:
                intel.career_dna.secondary_archetype = ranked[1][0]
        intel.career_dna.rationale = intel.career_dna.rationale or (
            "Inferred from your current title, skills, and role history until a full AI pass runs."
        )

    if not intel.functional.scores:
        intel.functional.scores = _heuristic_functional_scores(title, skills)

    if intel.trajectory.career_momentum_score is None and years:
        intel.trajectory.career_momentum_score = min(
            100, int(35 + min(float(years), 15) * 3 + role_count * 4)
        )

    if not intel.trajectory.growth_path and intel.experience.role_history:
        intel.trajectory.growth_path = [r.title for r in intel.experience.role_history if r.title][
            :6
        ]

    if not intel.goals.explicit_goals.desired_title and ctx.get("looking_for"):
        intel.goals.explicit_goals.desired_title = str(ctx["looking_for"])

    if not intel.prediction.most_likely_next_role.outcome:
        nxt = ctx.get("looking_for") or _next_title_step(ctx.get("current_title"))
        if nxt:
            intel.prediction.most_likely_next_role.outcome = str(nxt)
            intel.prediction.most_likely_next_role.confidence = min(
                85, 45 + int(min(float(years or 0), 12) * 2)
            )

    cp = ctx.get("career_profile") or {}
    gaps = (
        (cp.get("aspirations_market_fit_recommendations") or {})
        .get("career_path_recommendation", {})
        .get("gap_analysis")
    )
    if not intel.gap_analysis and isinstance(gaps, list):
        for gap in gaps[:3]:
            if isinstance(gap, dict) and gap.get("target_role"):
                intel.gap_analysis.append(
                    GapForRole(
                        target_role=str(gap["target_role"]),
                        missing_skills=[str(s) for s in (gap.get("missing_skills") or [])],
                    )
                )

    if intel.employability.employability_score is None:
        base = 40
        base += min(25, len(skills) * 2)
        base += min(20, int(min(float(years or 0), 15) * 1.5))
        intel.employability.employability_score = min(100, base)
        intel.employability.market_fit_score = intel.employability.market_fit_score or min(
            100, base + 5
        )
        intel.employability.technical_score = intel.employability.technical_score or min(
            100, 30 + len([s for s in skills if s in _TECH_HINTS]) * 8
        )

    if intel.leadership.leadership_stage is None and title:
        intel.leadership.leadership_stage = _infer_leadership_stage(title)

    if not intel.leadership.signals and intel.leadership.leadership_stage:
        stage = (intel.leadership.leadership_stage or "").casefold()
        if "manager" in stage or "director" in stage or "lead" in stage:
            intel.leadership.signals = ["Team leadership", "Stakeholder management"]

    summary = ctx.get("summary") or ""
    li_summary = ((ctx.get("linkedin_data") or {}).get("apify_profile") or {}).get("summary")
    if intel.brand.profile_completeness is None:
        text_len = len(str(summary or li_summary or ""))
        intel.brand.profile_completeness = min(100, 25 + text_len // 15)


_TECH_HINTS = frozenset(
    {
        "python",
        "java",
        "javascript",
        "typescript",
        "react",
        "sql",
        "aws",
        "docker",
        "kubernetes",
        "machine learning",
        "data",
    }
)


def _heuristic_archetype_scores(title: str, skills: list[str]) -> dict[str, int]:
    scores = {
        "Builder": 35,
        "Operator": 35,
        "Strategist": 35,
        "Innovator": 30,
        "Seller": 30,
        "Leader": 30,
        "Researcher": 25,
        "Creator": 25,
        "Advisor": 25,
    }
    blob = f"{title} {' '.join(skills)}"
    if any(k in blob for k in ("product", "strategy", "growth", "gtm")):
        scores["Strategist"] += 35
        scores["Leader"] += 20
    if any(k in blob for k in ("engineer", "developer", "software", "backend", "frontend")):
        scores["Builder"] += 40
    if any(k in blob for k in ("sales", "business development", "account")):
        scores["Seller"] += 40
    if any(k in blob for k in ("operations", "ops", "program")):
        scores["Operator"] += 35
    if any(k in blob for k in ("design", "creative", "content")):
        scores["Creator"] += 35
    if any(k in blob for k in ("research", "scientist", "analyst")):
        scores["Researcher"] += 35
    if any(k in blob for k in ("director", "head", "vp", "chief", "manager", "lead")):
        scores["Leader"] += 30
    return {k: min(100, v) for k, v in scores.items()}


def _heuristic_functional_scores(title: str, skills: list[str]) -> dict[str, int]:
    blob = f"{title} {' '.join(skills)}"
    scores = {
        "Sales": 20,
        "Marketing": 20,
        "Product": 20,
        "Engineering": 20,
        "Operations": 20,
        "Finance": 15,
        "HR": 15,
        "Customer Success": 15,
    }
    if any(k in blob for k in ("sales", "revenue", "bd", "account executive")):
        scores["Sales"] = 85
    if any(k in blob for k in ("marketing", "growth", "brand", "content")):
        scores["Marketing"] = 80
    if any(k in blob for k in ("product", "pm", "product manager")):
        scores["Product"] = 85
    if any(k in blob for k in ("engineer", "developer", "software", "sde")):
        scores["Engineering"] = 90
    if any(k in blob for k in ("operations", "ops", "revops", "supply")):
        scores["Operations"] = 80
    if any(k in blob for k in ("finance", "fp&a", "accounting")):
        scores["Finance"] = 75
    if any(k in blob for k in ("hr", "people", "talent", "recruiting")):
        scores["HR"] = 75
    if any(k in blob for k in ("customer success", "support", "csm")):
        scores["Customer Success"] = 80
    return scores


def _infer_leadership_stage(title: str) -> str:
    t = title.casefold()
    if any(k in t for k in ("chief", "cxo", "ceo", "cto", "cfo", "vp", "vice president")):
        return "Executive"
    if "director" in t:
        return "Director"
    if "manager" in t or "head of" in t:
        return "Manager"
    if "lead" in t or "team lead" in t:
        return "Team Lead"
    return "Individual Contributor"


def _next_title_step(current: str | None) -> str | None:
    if not current:
        return None
    t = current.strip()
    lower = t.casefold()
    if "senior" not in lower and "lead" not in lower and "head" not in lower:
        return f"Senior {t}"
    if "manager" not in lower and "director" not in lower:
        return f"{t} Manager"
    return None


def _overlay_chat_facts(intel: CareerIntelligence, ctx: dict[str, Any]) -> None:
    state = ctx.get("aarya_state") or {}
    facts = state.get("career_facts")
    if not isinstance(facts, dict):
        return

    prefs = intel.identity.career_preferences
    personal = intel.identity.personal_profile
    goals = intel.goals.explicit_goals

    _set_if_empty(personal, "preferred_name", facts.get("preferred_name"))
    _set_if_empty(personal, "relocation_preferences", facts.get("relocation_preferences"))
    _set_if_empty(personal, "work_authorization", facts.get("work_authorization"))
    _set_if_empty(personal, "visa_status", facts.get("visa_status"))
    _set_if_empty(personal, "citizenship", facts.get("citizenship"))

    _set_if_empty(prefs, "work_mode", facts.get("work_mode"))
    _set_if_empty(prefs, "travel_willingness", facts.get("travel_willingness"))
    _set_if_empty(prefs, "company_size_preference", facts.get("company_size_preference"))
    _set_if_empty(prefs, "startup_vs_enterprise", facts.get("startup_vs_enterprise"))

    ind_pref = facts.get("industry_preference")
    if isinstance(ind_pref, list) and ind_pref and not prefs.industry_preference:
        prefs.industry_preference = [str(x) for x in ind_pref]

    _set_if_empty(goals, "desired_title", facts.get("desired_title"))
    _set_if_empty(goals, "desired_industry", facts.get("desired_industry"))
    if facts.get("desired_salary") and goals.desired_salary is None:
        goals.desired_salary = _int_or_none(facts["desired_salary"])


def generate_open_questions(intel: CareerIntelligence) -> list[str]:
    """Gap-driven questions Aarya weaves into chat to fill the 24-layer profile."""
    questions: list[str] = []

    def add(q: str) -> None:
        if q not in questions and len(questions) < 8:
            questions.append(q)

    if not intel.goals.explicit_goals.desired_salary:
        add("What total compensation are you targeting (in LPA)?")
    if not intel.goals.explicit_goals.desired_title:
        add("What role or title do you want to grow into over the next 1-2 years?")
    if not intel.goals.explicit_goals.desired_industry:
        add("Which industries are you most interested in moving into?")
    if not intel.identity.career_preferences.work_mode:
        add("Do you prefer remote, hybrid, or onsite work?")
    if not intel.identity.personal_profile.relocation_preferences:
        add("Are you open to relocating, and if so, to which cities?")
    if intel.experience.total_years is None:
        add("How many years of full-time professional experience do you have?")
    if not intel.leadership.leadership_stage:
        add(
            "Would you describe yourself as an individual contributor, team lead, "
            "manager, or director-level today?"
        )
    if not intel.leadership.signals:
        add("Have you led hiring, mentoring, or owned a team budget? Tell me briefly.")
    if not intel.skills.soft_skills:
        add("What soft skills do colleagues most often praise you for?")
    if not intel.identity.career_preferences.travel_willingness:
        add("How much travel are you comfortable with for the right role?")
    if not intel.identity.career_preferences.startup_vs_enterprise:
        add("Do you lean toward startups, mid-size companies, or large enterprises?")
    if not intel.achievements.highlights:
        add("What's one measurable impact you are most proud of in your last role?")
    if not intel.brand.personal_brand_score:
        add("Do you post or engage on LinkedIn regularly, or mostly use it passively?")
    if not intel.compensation.current_market_value and not intel.compensation.salary_range.min:
        add("What is your current CTC, and what range would feel fair for your next move?")

    return questions[:8]


# ── helpers ──────────────────────────────────────────────────────────────────


def _map_roles(roles: list[Any]) -> list[RoleHistoryEntry]:
    out: list[RoleHistoryEntry] = []
    for role in roles[:15]:
        if not isinstance(role, dict):
            continue
        out.append(
            RoleHistoryEntry(
                title=_str_or_none(role.get("job_title") or role.get("title")),
                function=_str_or_none(role.get("function") or role.get("department")),
                department=_str_or_none(role.get("department")),
                industry=_str_or_none(role.get("industry")),
                seniority=_str_or_none(role.get("seniority_level") or role.get("seniority")),
                duration_months=_int_or_none(role.get("duration_months")),
                team_size=_int_or_none(role.get("team_size_managed") or role.get("team_size")),
                budget_ownership=_str_or_none(role.get("budget_ownership")),
            )
        )
    return out


def _map_linkedin_positions(positions: list[Any]) -> list[RoleHistoryEntry]:
    out: list[RoleHistoryEntry] = []
    for pos in positions[:15]:
        if not isinstance(pos, dict):
            continue
        out.append(
            RoleHistoryEntry(
                title=_str_or_none(pos.get("title")),
                industry=_str_or_none(pos.get("industry")),
                seniority=_str_or_none(pos.get("seniority")),
            )
        )
    return out


def _hard_skill(value: object) -> HardSkill:
    if isinstance(value, dict):
        return HardSkill(
            skill=str(value.get("skill") or value.get("name") or "").strip() or "skill",
            evidence=_str_or_none(value.get("evidence")),
            years=_float_or_none(value.get("years")),
            recency=_str_or_none(value.get("last_used") or value.get("recency")),
            proficiency=_str_or_none(value.get("proficiency") or value.get("level")),
        )
    return HardSkill(skill=str(value).strip())


def _copy_if_empty(obj: object, attr: str, value: object) -> None:
    if value and getattr(obj, attr, None) in (None, "", []):
        setattr(obj, attr, str(value) if not isinstance(value, list) else value)


def _set_if_empty(obj: object, attr: str, value: object) -> None:
    if value is not None and str(value).strip() and getattr(obj, attr, None) in (None, "", []):
        setattr(obj, attr, str(value).strip())


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
