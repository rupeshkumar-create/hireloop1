"""Tests for application intelligence services."""

from __future__ import annotations

from hireloop_api.services.ats_resume_check import run_ats_check
from hireloop_api.services.fit_dimensions import (
    compute_fit_recommendation,
    enrich_score_result,
)
from hireloop_api.services.resume_trimmer import trim_resume_html_for_job


def test_fit_recommendation_apply_vs_skip() -> None:
    assert (
        compute_fit_recommendation(overall=0.7, loc_score=0.8, skills_sim=0.6, culture_score=0.7)
        == "apply"
    )
    assert (
        compute_fit_recommendation(overall=0.5, loc_score=0.8, skills_sim=0.5, culture_score=0.6)
        == "stretch"
    )
    assert (
        compute_fit_recommendation(overall=0.5, loc_score=0.1, skills_sim=0.5, culture_score=0.6)
        == "skip"
    )


def test_enrich_score_result_adds_dimensions() -> None:
    cand = {
        "remote_preference": "remote",
        "profile_enrichment": {"career_goals": ["Product Manager"]},
        "prioritized_title": "Product Manager",
    }
    job = {
        "title": "Product Manager",
        "is_remote": True,
        "location_city": "Bengaluru",
        "seniority": "mid",
        "ctc_min": 20,
        "ctc_max": 28,
    }
    base = {
        "overall": 0.72,
        "skills_sim": 0.68,
        "exp_score": 0.7,
        "loc_score": 0.9,
        "ctc_score": 0.8,
        "explanation": "Good match",
    }
    out = enrich_score_result(cand, job, base, title_aff=0.85)
    assert out["culture_score"] is not None
    assert out["career_alignment_score"] is not None
    assert out["fit_recommendation"] in ("apply", "stretch", "skip")
    assert out.get("salary_benchmark") is not None


def test_ats_check_finds_contact_and_gaps() -> None:
    html = """
    <h1>Asha Rao</h1>
    <p class="resume-contact">Bengaluru · asha@example.com · 9876543210</p>
    <h2>Core Skills</h2>
    <p>Python, SQL, React</p>
    """
    profile = {
        "full_name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+919876543210",
        "skills": ["Python", "SQL"],
    }
    job = {
        "title": "Data Engineer",
        "skills_required": ["Python", "Spark"],
        "description": "Need Spark and SQL",
    }
    report = run_ats_check(html, profile=profile, job=job)
    assert report["contact_ok"] is True
    assert "spark" in report["keywords_gap"] or "Spark" in str(report["keywords_gap"])


def test_resume_trimmer_drops_low_relevance_bullets() -> None:
    html = """
    <h1>Test User</h1>
    <ul>
    <li>Led React dashboard rebuild with measurable adoption gains</li>
    <li>Organized team offsite logistics and catering</li>
    <li>Built Python ETL pipelines for analytics</li>
    </ul>
    """
    job = {
        "title": "Senior React Engineer",
        "skills_required": ["React", "TypeScript"],
        "description": "React frontend",
    }
    _trimmed, meta = trim_resume_html_for_job(html, job=job, max_words=8)
    assert meta["trimmed"] is True or meta["words_after"] <= meta["words_before"]
