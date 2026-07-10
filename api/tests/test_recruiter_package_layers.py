"""Tests for recruiter package layer services."""

from __future__ import annotations

from hireloop_api.services.role_interview_kit import generate_interview_kit
from hireloop_api.services.role_jd_bias import scan_jd_bias


def test_scan_jd_bias_passes_clean_jd() -> None:
    report = scan_jd_bias(
        "We are hiring a Senior Backend Engineer in Bengaluru. "
        "Must have Python, PostgreSQL, and 5+ years experience. "
        "Competitive salary and hybrid work."
    )
    assert report["passed"] is True
    assert report["score"] >= 80
    assert report["issues"] == []


def test_scan_jd_bias_flags_gendered_language() -> None:
    report = scan_jd_bias("Looking for a rockstar ninja developer. He must be young and energetic.")
    assert report["passed"] is False
    assert len(report["issues"]) >= 2
    categories = {i["category"] for i in report["issues"]}
    assert "gender" in categories or "age" in categories


def test_scan_jd_bias_short_jd() -> None:
    report = scan_jd_bias("Too short")
    assert report["passed"] is True
    assert "Add a job description" in report["summary"]


def test_generate_interview_kit_from_brief() -> None:
    role = {
        "title": "Backend Engineer",
        "hiring_brief": "Build APIs for payments team.",
        "must_haves": ["Python", "PostgreSQL"],
        "nice_to_haves": ["Kafka"],
        "evaluation_criteria": [
            {"criterion": "System design", "weight": 40},
            {"criterion": "Coding", "weight": 60},
        ],
    }
    kit = generate_interview_kit(role)
    assert kit["role_title"] == "Backend Engineer"
    assert len(kit["stages"]) >= 3
    assert len(kit["scorecard"]) >= 2
    assert any("Python" in q for stage in kit["stages"] for q in stage["questions"])
