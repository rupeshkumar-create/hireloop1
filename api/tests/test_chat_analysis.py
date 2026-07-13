"""Unit tests for chat resume / JD analysis (India-only)."""

from hireloop_api.services.chat_analysis import (
    analyze_jd_vs_profile,
    analyze_resume_parsed,
    analyze_resume_vs_role,
    looks_like_jd,
)


def test_looks_like_jd() -> None:
    short = "hi find me jobs"
    assert looks_like_jd(short) is False
    jd = (
        "We are hiring a Senior Backend Engineer.\n\n"
        "Responsibilities:\n- Build APIs\n\n"
        "Requirements:\n- 5 years of experience\n- Python, FastAPI\n"
        "Nice to have:\n- AWS\n"
    ) * 3
    assert looks_like_jd(jd) is True


def test_analyze_resume_gaps() -> None:
    parsed = {
        "full_name": "Riya",
        "current_title": "Product Manager",
        "current_company": "Acme",
        "years_experience": 6,
        "skills": ["roadmap", "sql", "stakeholder management", "analytics"],
        "location_city": None,
        "notice_period_days": None,
        "expected_ctc_min": None,
    }
    out = analyze_resume_parsed(parsed)
    assert out["kind"] == "resume_analysis"
    assert "Notice period" in out["gaps"]
    assert "Expected CTC (LPA)" in out["gaps"]
    assert "Preferred / current city" in out["gaps"]
    assert out["profile"]["current_title"] == "Product Manager"


def test_analyze_resume_version_compare() -> None:
    prev = {"skills": ["python"], "years_experience": 3}
    curr = {
        "skills": ["python", "fastapi"],
        "years_experience": 4,
        "notice_period_days": 30,
        "current_title": "Engineer",
    }
    out = analyze_resume_parsed(curr, previous=prev)
    assert out["version_compare"] is not None
    assert any("fastapi" in s for s in out["version_compare"]["skills_added"])


def test_analyze_jd_vs_profile() -> None:
    profile = {
        "full_name": "Asha",
        "current_title": "Backend Engineer",
        "years_experience": 5,
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "location_city": "Bengaluru",
    }
    jd = (
        "Backend Engineer — Bengaluru / Remote\n"
        "Requirements: Python, FastAPI, 4 years of experience\n"
        "Nice to have: Kubernetes\n"
        "Comp: 18-28 LPA\n"
    )
    out = analyze_jd_vs_profile(jd, profile)
    assert out["kind"] == "jd_fit_analysis"
    assert out["overall_score"] >= 50
    assert "skills" in out["section_scores"]
    assert out["should_apply"]["recommendation"] in {"yes", "maybe", "stretch"}
    assert out["salary_reality_check"]["unit"] == "LPA"
    assert len(out["mock_interview_questions"]) >= 8


def test_analyze_resume_vs_role() -> None:
    parsed = {
        "full_name": "Dev",
        "current_title": "SDE",
        "skills": ["python", "sql"],
        "years_experience": 4,
    }
    role = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "Backend Engineer",
        "must_haves": ["python", "fastapi"],
        "nice_to_haves": ["aws"],
        "jd_text": "Backend Engineer requirements: python fastapi 3 years",
        "location_city": "Pune",
        "comp_min": 1_500_000,
        "comp_max": 2_500_000,
    }
    out = analyze_resume_vs_role(
        parsed,
        role,
        skill_score=0.5,
        matched_skills=["python"],
        gap_skills=["fastapi"],
    )
    assert out["kind"] == "role_resume_analysis"
    assert out["role"]["title"] == "Backend Engineer"
    assert "fastapi" in out["must_haves"]["missing"]
    assert out["bias_safe_checklist"]
