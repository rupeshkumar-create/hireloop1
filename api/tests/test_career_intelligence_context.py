"""Tests for multi-source Career Intelligence context overlays."""

from hireloop_api.services.career_intelligence.context import (
    build_source_inventory,
    generate_open_questions,
    overlay_all_sources,
)
from hireloop_api.services.career_intelligence.schema import CareerIntelligence


def test_overlay_resume_linkedin_and_chat_facts() -> None:
    ctx = {
        "full_name": "Ada Lovelace",
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "years_experience": 8,
        "skills": ["python", "product"],
        "remote_preference": "remote_only",
        "career_profile": {
            "skills_competencies": {
                "soft_skills": ["Communication", "Leadership"],
                "emerging_skills": ["AI"],
            },
            "achievements_leadership": {
                "achievements_impact": {"revenue_influenced": "₹2Cr pipeline"},
                "leadership_experience": {"mentoring_experience": True},
            },
        },
        "linkedin_data": {
            "apify_profile": {
                "connectionsCount": 500,
                "skills": ["SaaS", "GTM"],
            }
        },
        "aarya_state": {
            "memory_summary": "Wants a remote VP Product role in SaaS.",
            "career_facts": {
                "desired_industry": "SaaS",
                "travel_willingness": "Minimal",
            },
        },
    }

    intel = overlay_all_sources(CareerIntelligence(), ctx)

    assert intel.identity.personal_profile.full_name == "Ada Lovelace"
    assert intel.identity.career_preferences.work_mode == "Remote"
    assert intel.experience.total_years == 8.0
    assert intel.skills.soft_skills == ["Communication", "Leadership"]
    assert intel.skills.future_skills == ["AI"]
    assert intel.achievements.revenue_influenced == "₹2Cr pipeline"
    assert "Mentoring" in intel.leadership.signals
    assert intel.network.connections == 500
    assert any(s.skill == "SaaS" for s in intel.skills.hard_skills)
    assert intel.goals.explicit_goals.desired_industry == "SaaS"


def test_source_inventory_lists_all_channels() -> None:
    inventory = build_source_inventory(
        {
            "career_profile": {"experience_career_history": {}},
            "career_analysis": {"employability": {}},
            "linkedin_data": {"apify_profile": {"name": "Test"}},
            "aarya_state": {
                "memory_summary": "Prefers remote.",
                "career_facts": {"work_mode": "Remote"},
            },
            "remote_preference": "remote_only",
        }
    )

    assert "Resume / CV" in inventory
    assert "LinkedIn: Apify" in inventory
    assert "Chat + voice" in inventory
    assert "structured career_facts" in inventory


def test_open_questions_cover_identity_and_compensation_gaps() -> None:
    intel = CareerIntelligence()
    questions = generate_open_questions(intel)

    assert len(questions) >= 5
    assert any("compensation" in q.lower() or "ctc" in q.lower() for q in questions)
    assert any("remote" in q.lower() or "hybrid" in q.lower() for q in questions)
