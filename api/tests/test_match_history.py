"""Job history must keep past matches even when live quality gates change."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from hireloop_api.routes.matches import _serialize_history_rows


def test_serialize_history_keeps_rows_that_fail_live_title_fit() -> None:
    """A new prioritized title must not erase previously scored jobs from history."""
    job_id = uuid4()
    candidate = {
        "current_title": "Senior Manager - Customer Success",
        "prioritized_title": "Senior Manager - Customer Success",
        "looking_for": "Customer Success",
        "skills": ["saas", "retention", "onboarding"],
        "headline": "CS leader",
        "summary": "",
        "years_experience": 10,
        "current_company": "Acme",
        "target_titles": ["Senior Manager - Customer Success"],
    }
    # Hotel sales role would fail should_persist_match vs CS title — history still keeps it.
    row = {
        "job_id": job_id,
        "title": "Hotel Sales Manager",
        "company_name": "Grand Hotel",
        "company_logo_url": None,
        "company_domain": None,
        "location_city": "Mumbai",
        "location_state": "MH",
        "is_remote": False,
        "employment_type": "full_time",
        "seniority": "senior",
        "ctc_min": None,
        "ctc_max": None,
        "salary_currency": "INR",
        "skills_required": ["sales", "hospitality"],
        "description": "Hotel sales",
        "apply_url": "https://example.com",
        "overall_score": 0.72,
        "skills_score": 0.5,
        "experience_score": 0.6,
        "location_score": 0.8,
        "ctc_score": None,
        "culture_score": None,
        "career_alignment_score": 0.4,
        "fit_recommendation": None,
        "salary_benchmark": None,
        "triage_notes": None,
        "explanation": "Previously matched",
        "llm_rationale": None,
        "llm_rationale_at": None,
        "computed_at": datetime(2026, 7, 1, tzinfo=UTC),
        "scraped_at": datetime(2026, 7, 1, tzinfo=UTC),
        "first_seen_at": datetime(2026, 7, 1, tzinfo=UTC),
        "last_seen_at": datetime(2026, 7, 2, tzinfo=UTC),
        "has_kit": False,
        "application_status": None,
        "intro_status": None,
    }

    items = _serialize_history_rows([row], candidate=candidate, min_score=0.0)
    assert len(items) == 1
    assert items[0]["job_id"] == str(job_id)
    assert items[0]["overall_score"] == 0.72
