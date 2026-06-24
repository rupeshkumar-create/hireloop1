import inspect
import uuid

from hireloop_api.agents.aarya.tools import job_search


def _job_search_source() -> str:
    return inspect.getsource(job_search)


def test_personalized_job_search_casts_nullable_parameters() -> None:
    source = _job_search_source()

    assert "$2::text = ''" in source
    assert "$4::text IS NULL" in source
    assert "$5::integer IS NULL" in source
    assert "LIMIT $6::integer" in source


def test_fallback_job_search_casts_nullable_parameters() -> None:
    source = _job_search_source()

    assert "$1::text = ''" in source
    assert "$3::text IS NULL" in source
    assert "$4::integer IS NULL" in source
    assert "LIMIT $5::integer" in source


async def test_job_search_falls_back_to_top_matches_when_query_filters_zero() -> None:
    # Regression: chat said "no jobs" while the Jobs panel showed 185. A narrow
    # query ("Growth Designer") that no live title contains zeroed out Step 1.
    # The candidate HAS ranked matches → Step 1b must return their top matches.
    cand_id = uuid.uuid4()
    match_row = {
        "id": uuid.uuid4(),
        "title": "Senior Product Manager (Growth)",
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "is_remote": False,
        "ctc_min": 1800000,
        "ctc_max": 3500000,
        "skills_required": ["growth", "product"],
        "employment_type": "full_time",
        "seniority": "senior",
        "apply_url": "https://example.test/job",
        "company_name": "Razorpay",
        "logo_url": None,
        "overall_score": 0.33,
        "explanation": "Strong growth fit",
    }

    class _DB:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
            return {"id": cand_id, "remote_preference": "any"}

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            has_scores = "ms.candidate_id" in query
            narrow = "ILIKE" in query
            if has_scores and not narrow:  # Step 1b: unfiltered top matches
                return [match_row]
            return []  # Step 1 (narrow query) + Step 2 (keyword) both empty

        async def execute(self, query: str, *args: object) -> str:
            return "INSERT 0 1"

    out = await job_search(
        _DB(),  # type: ignore[arg-type]
        str(uuid.uuid4()),
        "sess",
        "Growth Designer",  # niche title no live job contains
        ctc_min=1_000_000,
    )

    assert len(out) == 1
    assert out[0]["title"] == "Senior Product Manager (Growth)"
