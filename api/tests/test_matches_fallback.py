from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from hireloop_api.routes import matches


class FakeDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "public.candidates" in query
        return {
            "id": self.candidate_id,
            "current_title": "Software Engineer",
            "current_company": "Acme SaaS",
            "headline": "Backend platform engineer",
            "summary": "Builds B2B SaaS products",
            "years_experience": 5,
            "skills": ["python", "react", "sql"],
            "location_city": "Bengaluru",
            "location_state": "Karnataka",
            "expected_ctc_min": None,
            "expected_ctc_max": None,
            "remote_preference": "any",
            "open_to_relocation": False,
            "location_scope": "city",
            "target_titles": ["Backend Software Engineer"],
        }

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM public.match_scores" in query:
            return []
        if "FROM public.jobs" in query:
            return [
                {
                    "job_id": uuid.uuid4(),
                    "title": "Backend Software Engineer",
                    "company_name": "Acme India",
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "is_remote": False,
                    "employment_type": "full_time",
                    "seniority": "senior",
                    "ctc_min": None,
                    "ctc_max": None,
                    "skills_required": ["python", "sql"],
                    "description": "Build backend services for a B2B SaaS platform.",
                    "apply_url": "https://example.com/apply",
                    "skills_overlap": 2,
                    "scraped_at": datetime.now(UTC),
                }
            ]
        return []


@pytest.mark.asyncio
async def test_match_feed_falls_back_to_visible_jobs_when_scores_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_score_candidate(self: object, candidate_id: str, limit: int = 200) -> int:
        return 0

    monkeypatch.setattr(matches.MatchingEngine, "score_candidate", fake_score_candidate)

    result = await matches.get_match_feed(
        min_score=0,
        limit=10,
        offset=0,
        current_user={"id": str(uuid.uuid4())},
        db=FakeDb(),  # type: ignore[arg-type]
    )

    assert len(result) == 1
    assert result[0]["title"] == "Backend Software Engineer"
    assert result[0]["employment_type"] == "full_time"
    assert result[0]["overall_score"] > 0
    assert "Aarya" in (result[0]["explanation"] or "")


def test_fallback_drops_dental_sales_job_for_staffing_saas_gtm_candidate() -> None:
    candidate = {
        "current_title": "Go-To-Market Lead",
        "current_company": "Candidately",
        "headline": "B2B SaaS for staffing agencies",
        "summary": "AI resume builder and recruiting automation",
        "years_experience": 10,
        "skills": ["AI", "Digital Strategy", "Automation", "Sales"],
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "expected_ctc_min": None,
        "expected_ctc_max": None,
        "remote_preference": "any",
        "open_to_relocation": False,
        "location_scope": "city",
        "target_titles": ["Head of Sales", "VP Sales"],
    }
    dental_job = {
        "job_id": uuid.uuid4(),
        "title": "Sales Manager",
        "company_name": "SmileBright Dental Clinic",
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "is_remote": False,
        "employment_type": "full_time",
        "seniority": "senior",
        "ctc_min": None,
        "ctc_max": None,
        "skills_required": ["sales"],
        "description": "dental clinic healthcare practice growth and patient acquisition",
        "apply_url": "https://example.com/dental",
        "skills_overlap": 1,
        "scraped_at": datetime.now(UTC),
    }

    assert matches._serialize_fallback_match_row(dental_job, candidate=candidate) is None


def test_fallback_location_score_respects_country_scope() -> None:
    candidate = {
        "current_title": "Software Engineer",
        "current_company": "Acme SaaS",
        "headline": "Backend platform engineer",
        "summary": "Builds B2B SaaS products",
        "years_experience": 5,
        "skills": ["python", "sql"],
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "expected_ctc_min": None,
        "expected_ctc_max": None,
        "remote_preference": "any",
        "open_to_relocation": True,
        "location_scope": "country",
        "target_titles": ["Backend Software Engineer"],
    }
    far_city_job = {
        "job_id": uuid.uuid4(),
        "title": "Backend Software Engineer",
        "company_name": "Acme SaaS",
        "location_city": "Mumbai",
        "location_state": "Maharashtra",
        "is_remote": False,
        "employment_type": "full_time",
        "seniority": "senior",
        "ctc_min": None,
        "ctc_max": None,
        "skills_required": ["python", "sql"],
        "description": "Build backend services for a B2B SaaS platform.",
        "apply_url": "https://example.com/backend",
        "skills_overlap": 2,
        "scraped_at": datetime.now(UTC),
    }

    result = matches._serialize_fallback_match_row(far_city_job, candidate=candidate)

    assert result is not None
    assert result["location_score"] == 0.9
