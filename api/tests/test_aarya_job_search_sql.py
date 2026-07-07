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
            return {
                "id": cand_id,
                "remote_preference": "any",
                "market": "IN",
                "current_title": "Senior Product Manager, Growth",
                "current_company": "Razorpay",
                "full_name": "Candidate",
                "headline": "Growth product leader",
                "summary": "Builds payments growth loops and product-led growth systems",
                "years_experience": 8,
                "skills": ["growth", "product", "payments"],
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "expected_ctc_min": None,
                "expected_ctc_max": None,
                "open_to_relocation": False,
                "location_scope": "city",
            }

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

    assert len(out["matches"]) == 1
    assert out["matches"][0]["title"] == "Senior Product Manager (Growth)"


async def test_job_search_does_not_block_on_unprioritized_career_path() -> None:
    cand_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class _DB:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "COALESCE(NULLIF(c.market" in query:
                return {"market": "IN"}
            if "FROM public.career_paths" in query:
                return {
                    "id": uuid.uuid4(),
                    "current_role": "GTM Lead",
                    "summary": "Go-to-market leader",
                    "steps": [{"title": "Head of GTM"}],
                    "target_titles": ["Head of GTM"],
                    "target_locations": ["Bengaluru"],
                    "model": "test",
                    "prioritized_title": None,
                    "created_at": None,
                    "updated_at": None,
                }
            return {
                "id": cand_id,
                "remote_preference": "any",
                "market": "IN",
                "current_title": "GTM Lead",
                "current_company": "Candidately",
                "headline": "Staffing SaaS go-to-market leader",
                "summary": "AI resume builder for staffing agencies",
                "years_experience": 8,
                "skills": ["sales", "automation", "digital strategy"],
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "expected_ctc_min": None,
                "expected_ctc_max": None,
                "open_to_relocation": False,
                "location_scope": "city",
            }

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            if "FROM public.match_scores" not in query:
                return []
            return [
                {
                    "id": job_id,
                    "title": "Head of GTM - Staffing SaaS",
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "is_remote": False,
                    "ctc_min": None,
                    "ctc_max": None,
                    "skills_required": ["sales", "automation"],
                    "employment_type": "full_time",
                    "seniority": "lead",
                    "apply_url": "https://example.test/gtm",
                    "company_name": "RecruitOS",
                    "logo_url": None,
                    "description": "B2B SaaS platform for staffing and recruiting teams.",
                    "overall_score": 0.78,
                    "skills_score": 0.8,
                    "experience_score": 0.9,
                    "location_score": 1.0,
                    "ctc_score": 0.5,
                    "explanation": "Strong GTM SaaS fit",
                }
            ]

        async def execute(self, query: str, *args: object) -> str:
            return "INSERT 0 1"

    out = await job_search(
        _DB(),  # type: ignore[arg-type]
        str(uuid.uuid4()),
        "sess",
        "Head of GTM",
    )

    assert not out.get("blocked")
    assert len(out["matches"]) == 1
    assert out["matches"][0]["title"] == "Head of GTM - Staffing SaaS"


async def test_job_search_broadens_to_profile_fit_when_exact_title_and_city_are_empty() -> None:
    cand_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class _DB:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "COALESCE(NULLIF(c.market" in query:
                return {"market": "IN"}
            if "FROM public.career_paths" in query:
                return {
                    "id": uuid.uuid4(),
                    "current_role": "Assistant Manager",
                    "summary": "Customer-facing team lead",
                    "steps": [{"title": "Customer Success Manager"}],
                    "target_titles": ["Assistant Manager"],
                    "target_locations": ["Bengaluru"],
                    "model": "test",
                    "prioritized_title": "Assistant Manager",
                    "created_at": None,
                    "updated_at": None,
                }
            return {
                "id": cand_id,
                "remote_preference": "any",
                "market": "IN",
                "current_title": "Assistant Manager",
                "current_company": "The Wedding Company",
                "full_name": "Candidate",
                "headline": "Customer success and relationship management",
                "summary": "Client consultation, customer support, call quality monitoring.",
                "years_experience": 4,
                "skills": [
                    "Communication",
                    "Customer Success",
                    "client consultation",
                    "relationship management",
                    "call quality monitoring",
                    "Customer Support",
                ],
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "expected_ctc_min": None,
                "expected_ctc_max": None,
                "open_to_relocation": True,
                "location_scope": "country",
            }

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            if "FROM public.match_scores" in query:
                return []
            if "FROM public.jobs" not in query:
                return []
            # Exact query and token fallbacks should miss because this role does
            # not contain "Assistant Manager"; the broad profile fallback should
            # still surface it from the visible market pool.
            if "j.title ILIKE '%' || $1::text || '%'" in query:
                return []
            if "EXISTS (" in query:
                return []
            return [
                {
                    "id": job_id,
                    "title": "Customer Success Manager",
                    "location_city": "Mumbai",
                    "location_state": "Maharashtra",
                    "is_remote": True,
                    "ctc_min": None,
                    "ctc_max": None,
                    "skills_required": [
                        "Customer Success",
                        "Customer Support",
                        "Communication",
                    ],
                    "employment_type": "full_time",
                    "seniority": "mid",
                    "apply_url": "https://example.test/customer-success",
                    "company_name": "ClientOS",
                    "logo_url": None,
                    "description": "Own customer relationships, support quality, and retention.",
                    "overall_score": None,
                }
            ]

        async def execute(self, query: str, *args: object) -> str:
            return "INSERT 0 1"

    out = await job_search(
        _DB(),  # type: ignore[arg-type]
        str(uuid.uuid4()),
        "sess",
        "Assistant Manager",
        location_city="Bengaluru",
    )

    assert len(out["matches"]) == 1
    assert out["matches"][0]["title"] == "Customer Success Manager"
    assert len(out["job_cards"]) == 1


async def test_job_search_drops_dental_sales_for_staffing_saas_gtm_candidate() -> None:
    cand_id = uuid.uuid4()

    class _DB:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "COALESCE(NULLIF(c.market" in query:
                return {"market": "IN"}
            if "FROM public.career_paths" in query:
                return None
            return {
                "id": cand_id,
                "remote_preference": "any",
                "market": "IN",
                "current_title": "GTM Lead",
                "current_company": "Candidately",
                "headline": "B2B SaaS for staffing agencies",
                "summary": "AI resume builder and recruiting automation",
                "years_experience": 8,
                "skills": ["sales", "automation", "digital strategy"],
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "expected_ctc_min": None,
                "expected_ctc_max": None,
                "open_to_relocation": False,
                "location_scope": "city",
            }

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            if "FROM public.match_scores" not in query:
                return []
            return [
                {
                    "id": uuid.uuid4(),
                    "title": "Sales Manager",
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                    "is_remote": False,
                    "ctc_min": None,
                    "ctc_max": None,
                    "skills_required": ["sales"],
                    "employment_type": "full_time",
                    "seniority": "senior",
                    "apply_url": "https://example.test/dental",
                    "company_name": "SmileBright Dental Clinic",
                    "logo_url": None,
                    "description": "Dental clinic healthcare practice growth and patient acquisition.",
                    "overall_score": 0.8,
                    "skills_score": 0.8,
                    "experience_score": 0.8,
                    "location_score": 1.0,
                    "ctc_score": 0.5,
                    "explanation": "Stale generic sales score",
                }
            ]

        async def execute(self, query: str, *args: object) -> str:
            return "INSERT 0 1"

    out = await job_search(
        _DB(),  # type: ignore[arg-type]
        str(uuid.uuid4()),
        "sess",
        "sales",
    )

    assert out["matches"] == []
    assert out["job_cards"] == []
