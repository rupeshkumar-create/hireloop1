from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from hireloop_api.config import Settings
from hireloop_api.routes import matches


def _test_settings() -> Settings:
    return Settings(_env_file=None, environment="test", apify_token="", openrouter_api_key="")  # type: ignore[call-arg]


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
            "aarya_state": {},
            "market": "IN",
            "target_titles": ["Backend Software Engineer"],
        }

    async def fetchval(self, query: str, *args: object) -> int:
        return 0

    async def executemany(self, query: str, args: object) -> None:
        return None

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


class CachedAccorDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "public.candidates" in query
        return {
            "id": self.candidate_id,
            "current_title": "Go-To-Market Lead",
            "current_company": "Candidately",
            "headline": "Helping recruiters turn resumes into client-ready submissions",
            "summary": "B2B SaaS GTM for staffing agencies, Bullhorn workflows, demos, adoption, onboarding.",
            "years_experience": 10,
            "skills": ["Artificial Intelligence", "Digital Strategy", "Automation", "Sales"],
            "location_city": "Bengaluru",
            "location_state": "Karnataka",
            "expected_ctc_min": None,
            "expected_ctc_max": None,
            "remote_preference": "any",
            "open_to_relocation": False,
            "location_scope": "country",
            "aarya_state": {},
            "market": "IN",
            "target_titles": ["Head of GTM", "Sales Operations Lead", "GTM Lead"],
        }

    async def fetchval(self, query: str, *args: object) -> int:
        return 0

    async def executemany(self, query: str, args: object) -> None:
        return None

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM public.match_scores" in query:
            return [
                {
                    "job_id": uuid.uuid4(),
                    "title": "Associate Director of Sales - Mumbai",
                    "company_name": "AccorHotel",
                    "location_city": "Mumbai",
                    "location_state": "Maharashtra",
                    "is_remote": False,
                    "employment_type": "full_time",
                    "seniority": "director",
                    "ctc_min": None,
                    "ctc_max": None,
                    "salary_currency": "INR",
                    "skills_required": ["sales", "hospitality"],
                    "description": "Accor hospitality hotel sales leadership in Mumbai.",
                    "apply_url": "https://example.com/accor",
                    "overall_score": 0.56,
                    "skills_score": 0.8,
                    "experience_score": 0.9,
                    "location_score": 0.9,
                    "ctc_score": 0.5,
                    "explanation": "Moderate match from an old scoring run.",
                    "llm_rationale": None,
                    "llm_rationale_at": None,
                    "computed_at": datetime.now(UTC),
                    "has_kit": False,
                    "intro_status": None,
                }
            ]
        if "FROM public.jobs" in query:
            return [
                {
                    "job_id": uuid.uuid4(),
                    "title": "Go-To-Market Lead - Staffing SaaS",
                    "company_name": "RecruitOS",
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "is_remote": True,
                    "employment_type": "full_time",
                    "seniority": "lead",
                    "ctc_min": None,
                    "ctc_max": None,
                    "salary_currency": "INR",
                    "skills_required": [
                        "sales",
                        "saas",
                        "staffing",
                        "automation",
                        "artificial intelligence",
                    ],
                    "description": (
                        "Own GTM for an AI automation B2B SaaS platform used by staffing "
                        "agencies, recruiters, and onboarding teams."
                    ),
                    "apply_url": "https://example.com/recruitos",
                    "skills_overlap": 1,
                    "scraped_at": datetime.now(UTC),
                }
            ]
        return []


class CachedAccorOnlyDb(CachedAccorDb):
    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM public.match_scores" in query:
            return await super().fetch(query, *args)
        return []

    async def fetchval(self, query: str, *args: object) -> int:
        assert "FROM public.match_scores" in query
        return 1


class MatchFeedTestJobsOnlyDb:
    """Cached scores contain only Hireschema test roles — market feed must still load."""

    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "public.candidates" in query
        return {
            "id": self.candidate_id,
            "current_title": "Go-To-Market Lead",
            "current_company": "Candidately",
            "headline": "B2B SaaS GTM",
            "summary": "Staffing SaaS growth",
            "years_experience": 10,
            "skills": ["sales", "marketing", "automation"],
            "location_city": "Bengaluru",
            "location_state": "Karnataka",
            "expected_ctc_min": None,
            "expected_ctc_max": None,
            "remote_preference": "any",
            "open_to_relocation": False,
            "location_scope": "country",
            "aarya_state": {},
            "market": "IN",
            "target_titles": ["Head of GTM"],
        }

    async def fetchval(self, query: str, *args: object) -> int:
        return 0

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "FROM public.match_scores" in query:
            return [
                {
                    "job_id": uuid.uuid4(),
                    "title": "Go-To-Market Lead — AI Resume Builder (Staffing SaaS)",
                    "company_name": "Hireschema Test Co",
                    "company_domain": "hireschema-test.com",
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "is_remote": True,
                    "employment_type": "full_time",
                    "seniority": "lead",
                    "ctc_min": None,
                    "ctc_max": None,
                    "salary_currency": "INR",
                    "skills_required": ["sales", "saas"],
                    "description": "Internal test role.",
                    "apply_url": "https://example.com/test",
                    "overall_score": 0.75,
                    "skills_score": 0.75,
                    "experience_score": 0.75,
                    "location_score": 0.75,
                    "ctc_score": 0.75,
                    "explanation": "Hireschema test role",
                    "llm_rationale": None,
                    "llm_rationale_at": None,
                    "computed_at": datetime.now(UTC),
                    "has_kit": False,
                    "intro_status": None,
                }
            ]
        if "FROM public.jobs" in query:
            return [
                {
                    "job_id": uuid.uuid4(),
                    "title": "Growth Manager",
                    "company_name": "DrinkPrime",
                    "company_domain": None,
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "is_remote": False,
                    "employment_type": "full_time",
                    "seniority": "senior",
                    "ctc_min": None,
                    "ctc_max": None,
                    "salary_currency": "INR",
                    "skills_required": ["marketing", "growth"],
                    "description": "Own growth for a consumer subscription brand.",
                    "apply_url": "https://example.com/growth",
                    "skills_overlap": 1,
                    "scraped_at": datetime.now(UTC),
                }
            ]
        return []

    async def executemany(self, query: str, args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_match_feed_supplements_market_jobs_when_cache_only_has_test_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_embed_score(*_a: object, **_kw: object) -> tuple[int, int]:
        return 0, 0

    monkeypatch.setattr(
        "hireloop_api.services.embeddings.embed_pending_and_score_candidate",
        fake_embed_score,
    )
    monkeypatch.setattr(matches, "get_settings", _test_settings)

    result = await matches.get_match_feed(
        min_score=0.38,
        limit=10,
        offset=0,
        current_user={"id": str(uuid.uuid4())},
        db=MatchFeedTestJobsOnlyDb(),  # type: ignore[arg-type]
    )

    companies = [row["company_name"] for row in result]
    assert "DrinkPrime" in companies
    assert companies[0] == "DrinkPrime"


@pytest.mark.asyncio
async def test_match_feed_falls_back_to_visible_jobs_when_scores_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_embed_score(*_a: object, **_kw: object) -> tuple[int, int]:
        return 0, 0

    monkeypatch.setattr(
        "hireloop_api.services.embeddings.embed_pending_and_score_candidate",
        fake_embed_score,
    )
    monkeypatch.setattr(matches, "get_settings", _test_settings)

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


@pytest.mark.asyncio
async def test_match_feed_filters_stale_cached_accor_row_and_uses_strict_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_embed_score(*_a: object, **_kw: object) -> tuple[int, int]:
        return 0, 0

    monkeypatch.setattr(
        "hireloop_api.services.embeddings.embed_pending_and_score_candidate",
        fake_embed_score,
    )
    monkeypatch.setattr(matches, "get_settings", _test_settings)
    result = await matches.get_match_feed(
        min_score=0.45,
        limit=10,
        offset=0,
        current_user={"id": str(uuid.uuid4())},
        db=CachedAccorDb(),  # type: ignore[arg-type]
    )

    assert [row["company_name"] for row in result] == ["RecruitOS"]
    assert result[0]["title"] == "Go-To-Market Lead - Staffing SaaS"


@pytest.mark.asyncio
async def test_match_count_ignores_stale_cached_accor_row() -> None:
    result = await matches.get_match_feed_count(
        min_score=0.45,
        current_user={"id": str(uuid.uuid4())},
        db=CachedAccorOnlyDb(),  # type: ignore[arg-type]
    )

    assert result == {"total": 0}


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
