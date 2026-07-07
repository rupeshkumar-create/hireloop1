from __future__ import annotations

import uuid

from hireloop_api.routes.me import list_saved_jobs


class _SavedJobsDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "public.candidates" in query
        return {
            "id": self.candidate_id,
            "current_title": "GTM Lead",
            "current_company": "Higher Schema",
            "looking_for": "Go-to-Market Lead",
            "prioritized_title": "Go-to-Market Lead",
            "headline": "B2B SaaS GTM",
            "summary": "Go-to-market for AI recruiting SaaS.",
            "years_experience": 4,
            "skills": ["GTM", "Sales", "B2B SaaS"],
            "expected_ctc_min": None,
            "expected_ctc_max": None,
            "location_city": "Bengaluru",
            "location_state": "Karnataka",
            "remote_preference": "any",
            "open_to_relocation": False,
            "location_scope": "country",
            "target_titles": ["Go-to-Market Lead"],
        }

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "FROM public.saved_jobs" in query
        return [
            {
                "job_id": self.job_id,
                "title": "AI Native Team Quality Tester",
                "company_name": "Example Co",
                "company_logo_url": None,
                "company_domain": None,
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "is_remote": False,
                "employment_type": "full_time",
                "seniority": "junior",
                "ctc_min": None,
                "ctc_max": None,
                "salary_currency": "INR",
                "skills_required": ["QA", "Testing"],
                "description": "Run quality checks for AI outputs.",
                "apply_url": "https://example.com/job",
                "overall_score": None,
                "skills_score": None,
                "experience_score": None,
                "location_score": None,
                "ctc_score": None,
                "explanation": None,
                "computed_at": None,
                "saved_at": None,
            }
        ]


async def test_saved_jobs_compute_fallback_score_when_match_score_missing() -> None:
    db = _SavedJobsDb()

    rows = await list_saved_jobs(
        current_user={"id": "11111111-1111-1111-1111-111111111111"},
        db=db,  # type: ignore[arg-type]
    )

    assert len(rows) == 1
    assert rows[0]["overall_score"] != 0.5
    assert rows[0]["overall_score"] < 0.5
    assert rows[0]["skills_score"] is not None
