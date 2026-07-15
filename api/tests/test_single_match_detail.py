"""Regression: GET /matches/{job_id} must not 500 on low-score / null timestamps."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from hireloop_api.routes import matches


def test_serialize_single_match_detail_handles_null_computed_at() -> None:
    job_id = uuid.uuid4()
    row = {
        "job_id": job_id,
        "title": "Backend Engineer",
        "company_name": "Acme",
        "company_logo_url": None,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "is_remote": None,  # must not blow up bool()
        "employment_type": "full_time",
        "seniority": "mid",
        "ctc_min": 20,
        "ctc_max": 30,
        "salary_currency": "INR",
        "skills_required": ["Python", "SQL"],
        "apply_url": "https://example.com",
        "description": "Build APIs",
        "requirements": "3+ years",
        "scraped_at": datetime.now(UTC),
        "overall_score": 0.42,
        "skills_score": 0.5,
        "experience_score": 0.4,
        "location_score": 1.0,
        "ctc_score": 0.5,
        "culture_score": None,
        "career_alignment_score": None,
        "fit_recommendation": None,
        "salary_benchmark": '{"band":"ok"}',  # string JSON from driver
        "triage_notes": None,
        "explanation": "Solid skills overlap",
        "computed_at": None,
    }
    out = matches._serialize_single_match_detail(
        row, candidate={"skills": ["Python", "React"]}
    )
    assert out["job_id"] == str(job_id)
    assert out["computed_at"] is None
    assert out["is_remote"] is False
    assert out["salary_benchmark"] == {"band": "ok"}
    assert out["skills_matched"] == ["Python"]
    assert out["skills_gap"] == ["SQL"]
    assert out["posted_at"] is not None


@pytest.mark.asyncio
async def test_get_single_match_low_score_does_not_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """score_pair can return a float without persisting — detail page must still render."""
    candidate_id = uuid.uuid4()
    job_id = uuid.uuid4()
    user_id = uuid.uuid4()

    calls: list[str] = []

    class FakeDb:
        async def fetchrow(self, query: str, *args: object) -> dict | None:
            q = " ".join(query.split())
            if "FROM public.candidates WHERE user_id" in q:
                return {"id": candidate_id, "skills": ["python"]}
            if "FROM public.match_scores ms" in q:
                calls.append("match_scores")
                return None
            if "FROM public.jobs j" in q and "AS job_id" in q:
                calls.append("job_detail")
                return {
                    "job_id": job_id,
                    "title": "Dental Office Manager",
                    "company_name": "Bright Smiles",
                    "company_logo_url": None,
                    "company_domain": None,
                    "location_city": "Mumbai",
                    "location_state": "Maharashtra",
                    "is_remote": False,
                    "employment_type": "full_time",
                    "seniority": "mid",
                    "ctc_min": None,
                    "ctc_max": None,
                    "salary_currency": "INR",
                    "skills_required": ["Dentistry"],
                    "apply_url": "https://example.com/apply",
                    "description": "Manage clinic ops",
                    "requirements": None,
                    "scraped_at": datetime.now(UTC),
                }
            if "FROM public.candidates WHERE id" in q:
                return {
                    "id": candidate_id,
                    "skills": ["python"],
                    "current_title": "Software Engineer",
                    "years_experience": 5,
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "expected_ctc_min": None,
                    "expected_ctc_max": None,
                    "remote_preference": "any",
                    "open_to_relocation": False,
                    "location_scope": "city",
                    "current_company": "Acme",
                    "headline": None,
                    "summary": None,
                }
            return None

    async def fake_market(_db: object, _cid: object) -> str:
        return "IN"

    class FakeEngine:
        def __init__(self, _db: object) -> None:
            pass

        async def score_pair(self, *_a: object, **_k: object) -> float:
            # Low score that matching engine returns without persisting
            return 0.12

    monkeypatch.setattr(matches, "fetch_candidate_market", fake_market)
    monkeypatch.setattr(matches, "MatchingEngine", FakeEngine)

    result = await matches.get_single_match(
        str(job_id),
        current_user={"id": str(user_id), "market": "IN"},
        db=FakeDb(),  # type: ignore[arg-type]
    )
    assert result["job_id"] == str(job_id)
    assert result["title"] == "Dental Office Manager"
    assert "overall_score" in result
    assert "job_detail" in calls


@pytest.mark.asyncio
async def test_get_single_match_fallback_none_becomes_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class FakeDb:
        async def fetchrow(self, query: str, *args: object) -> dict | None:
            q = " ".join(query.split())
            if "FROM public.candidates WHERE user_id" in q:
                return {"id": candidate_id, "skills": []}
            if "FROM public.match_scores ms" in q:
                return None
            if "FROM public.jobs j" in q and "AS job_id" in q:
                return {
                    "job_id": job_id,
                    "title": "X",
                    "company_name": "Y",
                    "company_logo_url": None,
                    "company_domain": None,
                    "location_city": None,
                    "location_state": None,
                    "is_remote": False,
                    "employment_type": None,
                    "seniority": None,
                    "ctc_min": None,
                    "ctc_max": None,
                    "salary_currency": None,
                    "skills_required": [],
                    "apply_url": None,
                    "description": None,
                    "requirements": None,
                    "scraped_at": None,
                }
            if "FROM public.candidates WHERE id" in q:
                return {"id": candidate_id, "skills": []}
            return None

    class FakeEngine:
        def __init__(self, _db: object) -> None:
            pass

        async def score_pair(self, *_a: object, **_k: object) -> float:
            return 0.01

    monkeypatch.setattr(matches, "fetch_candidate_market", AsyncMock(return_value="IN"))
    monkeypatch.setattr(matches, "MatchingEngine", FakeEngine)
    monkeypatch.setattr(matches, "_serialize_fallback_match_row", lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        await matches.get_single_match(
            str(job_id),
            current_user={"id": str(uuid.uuid4()), "market": "IN"},
            db=FakeDb(),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404
