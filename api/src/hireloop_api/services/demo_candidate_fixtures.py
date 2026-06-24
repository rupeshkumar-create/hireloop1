"""
Rich demo candidate profiles for marketplace seeds — experience, education, and
full deterministic Career Intelligence (no LLM required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hireloop_api.services.career_intelligence.engine import _completeness, _seed_from_context

# Prior roles per demo candidate (current role comes from seed dict).
_DEMO_PRIOR_ROLES: dict[str, list[dict[str, Any]]] = {
    "priya.candidate@hireloop.in": [
        {
            "title": "Backend Engineer",
            "company": "Freshworks",
            "start_date": "2018",
            "end_date": "2021",
            "location": "Chennai",
            "description": "Built customer-facing APIs and internal tooling on PostgreSQL.",
            "highlights": ["API platform", "PostgreSQL performance tuning"],
        },
    ],
    "rahul.candidate@hireloop.in": [
        {
            "title": "Frontend Engineer",
            "company": "CRED",
            "start_date": "2019",
            "end_date": "2022",
            "location": "Bengaluru",
            "description": "Shipped trading dashboards and design-system components.",
            "highlights": ["React performance", "Design systems"],
        },
    ],
    "ananya.candidate@hireloop.in": [
        {
            "title": "Data Scientist",
            "company": "Ola",
            "start_date": "2019",
            "end_date": "2023",
            "location": "Bengaluru",
            "description": "Demand forecasting and experimentation for mobility products.",
            "highlights": ["Time-series models", "A/B testing"],
        },
    ],
    "vikram.candidate@hireloop.in": [
        {
            "title": "Product Manager",
            "company": "Paytm",
            "start_date": "2018",
            "end_date": "2021",
            "location": "Noida",
            "description": "Owned payments onboarding and merchant growth loops.",
            "highlights": ["0-to-1 launches", "Growth analytics"],
        },
    ],
    "meera.candidate@hireloop.in": [
        {
            "title": "Marketing Specialist",
            "company": "Urban Company",
            "start_date": "2019",
            "end_date": "2022",
            "location": "Bengaluru",
            "description": "Paid social and lifecycle campaigns for consumer apps.",
            "highlights": ["Meta ads", "Retention campaigns"],
        },
    ],
    "karan.candidate@hireloop.in": [
        {
            "title": "DevOps Engineer",
            "company": "Myntra",
            "start_date": "2018",
            "end_date": "2021",
            "location": "Bengaluru",
            "description": "Kubernetes platform and CI/CD for e-commerce peak traffic.",
            "highlights": ["K8s migrations", "Terraform modules"],
        },
    ],
}

_DEMO_EDUCATION: dict[str, list[dict[str, Any]]] = {
    "priya.candidate@hireloop.in": [
        {
            "degree": "B.Tech Computer Science",
            "institution": "NIT Trichy",
            "field_of_study": "Computer Science",
            "end_date": "2018",
        },
    ],
    "rahul.candidate@hireloop.in": [
        {
            "degree": "B.E. Information Technology",
            "institution": "BITS Pilani",
            "field_of_study": "IT",
            "end_date": "2018",
        },
    ],
    "ananya.candidate@hireloop.in": [
        {
            "degree": "M.Tech AI",
            "institution": "IIT Madras",
            "field_of_study": "Machine Learning",
            "end_date": "2019",
        },
    ],
    "vikram.candidate@hireloop.in": [
        {
            "degree": "B.Tech",
            "institution": "Delhi College of Engineering",
            "field_of_study": "Electronics",
            "end_date": "2016",
        },
    ],
    "meera.candidate@hireloop.in": [
        {
            "degree": "MBA Marketing",
            "institution": "NMIMS Mumbai",
            "field_of_study": "Marketing",
            "end_date": "2018",
        },
    ],
    "karan.candidate@hireloop.in": [
        {
            "degree": "B.Tech",
            "institution": "IIIT Hyderabad",
            "field_of_study": "Computer Science",
            "end_date": "2017",
        },
    ],
}


def demo_career_profile(candidate: dict[str, Any]) -> dict[str, Any]:
    email = str(candidate.get("email") or "").lower()
    current = {
        "title": candidate["current_title"],
        "company": candidate["current_company"],
        "start_date": str(max(2018, 2026 - int(candidate.get("years_experience", 5)))),
        "end_date": None,
        "location": candidate.get("city") or candidate.get("location_city"),
        "description": candidate.get("summary"),
        "highlights": [
            f"Core delivery at {candidate['current_company']}",
            "Cross-functional collaboration",
        ],
    }
    prior = list(_DEMO_PRIOR_ROLES.get(email, []))
    roles = [current, *prior]
    education = _DEMO_EDUCATION.get(
        email,
        [
            {"degree": "B.Tech", "institution": "Indian university", "end_date": "2018"},
        ],
    )
    skills = candidate.get("skills") or []
    return {
        "profile_demographics": {
            "languages_spoken": ["English", "Hindi"],
            "preferred_work_location": candidate.get("city") or candidate.get("location_city"),
            "nationality_work_authorization": "Indian citizen",
        },
        "experience_career_history": {
            "roles": roles,
            "derived_metrics": {
                "total_experience": candidate.get("years_experience"),
                "average_tenure": 2.5,
            },
        },
        "education_credentials": {"education": education},
        "skills_competencies": {
            "technical_skills": skills,
            "core_skills": skills[:4],
        },
        "aspirations_market_fit_recommendations": {
            "career_path_recommendation": {
                "career_progression_analysis": {
                    "title_growth": [r["title"] for r in reversed(roles) if r.get("title")],
                },
                "gap_analysis": [
                    {
                        "target_role": candidate.get("target_titles", ["Next role"])[0],
                        "missing_skills": [],
                    },
                ],
            },
        },
    }


def demo_parsed_resume(candidate: dict[str, Any]) -> dict[str, Any]:
    cp = demo_career_profile(candidate)
    roles = cp["experience_career_history"]["roles"]
    work_experience = []
    for r in roles:
        work_experience.append(
            {
                "title": r.get("title"),
                "company": r.get("company"),
                "start_date": r.get("start_date"),
                "end_date": r.get("end_date"),
                "description": r.get("description"),
                "location": r.get("location"),
                "is_current": r.get("end_date") is None,
            }
        )
    education = cp["education_credentials"]["education"]
    return {
        "work_experience": work_experience,
        "education": [
            {
                "institution": e.get("institution"),
                "degree": e.get("degree"),
                "field_of_study": e.get("field_of_study"),
                "end_date": e.get("end_date"),
            }
            for e in education
        ],
        "skills": list(candidate.get("skills") or []),
        "years_experience": candidate.get("years_experience"),
    }


def demo_candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    career_profile = demo_career_profile(candidate)
    return {
        "full_name": candidate.get("full_name"),
        "current_title": candidate.get("current_title"),
        "current_company": candidate.get("current_company"),
        "years_experience": candidate.get("years_experience"),
        "location_city": candidate.get("city") or candidate.get("location_city"),
        "location_state": candidate.get("state") or candidate.get("location_state"),
        "skills": candidate.get("skills"),
        "headline": candidate.get("headline"),
        "summary": candidate.get("summary"),
        "expected_ctc_min": candidate.get("ctc_min"),
        "expected_ctc_max": candidate.get("ctc_max"),
        "current_ctc": candidate.get("current_ctc"),
        "notice_period_days": 30,
        "looking_for": candidate.get("looking_for"),
        "remote_preference": candidate.get("remote_preference"),
        "career_profile": career_profile,
    }


def demo_career_intelligence_blob(candidate: dict[str, Any]) -> dict[str, Any]:
    ctx = demo_candidate_context(candidate)
    intel = _seed_from_context(ctx)
    blob = intel.model_dump(mode="json")
    blob["data_completeness"] = _completeness(ctx)
    blob["model"] = "seed"
    blob["open_questions"] = [
        "Are you open to early-stage startups or only established companies?",
        "What's your ideal team size and management style?",
    ]
    # Mobility from target titles
    targets = candidate.get("target_titles") or []
    if targets and not blob.get("mobility", {}).get("adjacent_roles"):
        blob.setdefault("mobility", {})
        blob["mobility"]["adjacent_roles"] = [
            {
                "role": t,
                "kind": "adjacent",
                "feasibility_score": 78,
                "time_required": "6-12 months",
                "skill_gap": [],
            }
            for t in targets[:3]
        ]
    blob["updated_at"] = datetime.now(UTC).isoformat()
    return blob
