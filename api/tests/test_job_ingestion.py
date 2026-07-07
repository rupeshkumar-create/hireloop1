"""
Tests for the Apify job ingestion pipeline (P09).

These exercise the pure normalisation logic and the DB upsert path without
needing a real Apify token, network, or Postgres connection:

  * Multi-market normalisation (IN / US / GB) produces supported JobRecords.
  * Salary / location / skill / dedup-id parsing for Google Jobs payloads.
  * JobIngester._upsert_jobs insert / update / skip accounting via a fake conn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from hireloop_api.services.apify import job_ingester as job_ingester_module
from hireloop_api.services.apify.candidate_job_query_plan import CandidateJobIngestPlan
from hireloop_api.services.apify.job_ingester import (
    JobIngester,
    derive_ingest_locations,
    derive_ingest_queries,
)
from hireloop_api.services.apify.jobs_scraper import ApifyJobsScraper, JobRecord

# ── JobRecord model invariants ────────────────────────────────────────────────


def test_country_code_accepts_supported_markets() -> None:
    rec = JobRecord(apify_job_id="x1", title="Engineer", country_code="US")
    assert rec.country_code == "US"


def test_employment_type_is_normalised() -> None:
    assert JobRecord(apify_job_id="x", title="t", employment_type="Full-Time").employment_type == (
        "full_time"
    )
    assert JobRecord(apify_job_id="x", title="t", employment_type="weird").employment_type == (
        "full_time"
    )


def test_seniority_maps_known_levels_and_drops_unknown() -> None:
    assert JobRecord(apify_job_id="x", title="t", seniority="Mid-Senior level").seniority == "mid"
    assert JobRecord(apify_job_id="x", title="t", seniority="nonsense").seniority is None


# ── ApifyJobsScraper (Google Jobs) input + normalisation ──────────────────────


def _google_jobs_scraper() -> ApifyJobsScraper:
    return ApifyJobsScraper(api_token="test-token")


def test_google_jobs_input_uses_johnvc_schema() -> None:
    scraper = _google_jobs_scraper()

    payload = scraper._build_google_jobs_input(
        query="Customer Success Manager",
        location="Bengaluru, India",
        max_results=100,
        country="in",
    )

    assert payload == {
        "query": "Customer Success Manager",
        "location": "Bengaluru, India",
        "country": "in",
        "language": "None",
        "google_domain": "google.com",
        "num_results": 100,
        "max_pagination": 0,
        "include_lrad": False,
        "lrad_value": "",
        "max_delay": 1,
        "output_file": "",
        "cleanup_results": True,
    }
    assert scraper._google_country_code("GB") == "uk"


def test_google_jobs_normalises_valid_india_job() -> None:
    scraper = _google_jobs_scraper()
    raw = {
        "title": "Customer Success Manager",
        "company_name": "ClientOS",
        "location": "Bengaluru, Karnataka, India",
        "description": "Own renewals, customer support, communication, and relationship management.",
        "job_id": "google-job-123",
        "detected_extensions": {"schedule_type": "Full-time"},
        "apply_options": [{"title": "Company site", "link": "https://clientos.example/jobs/123"}],
    }

    rec = scraper.normalise(raw)

    assert rec is not None
    assert rec.apify_job_id == "gj_google-job-123"
    assert rec.title == "Customer Success Manager"
    assert rec.company_name == "ClientOS"
    assert rec.country_code == "IN"
    assert rec.location_city == "Bengaluru"
    assert rec.location_state == "Karnataka"
    assert rec.employment_type == "full_time"
    assert rec.apply_url == "https://clientos.example/jobs/123"
    assert "customer support" in rec.skills_required


def test_google_jobs_accepts_us_location() -> None:
    scraper = _google_jobs_scraper()
    raw = {
        "title": "Senior Engineer",
        "location": "San Francisco, CA, USA",
        "jobUrl": "https://jobs.google.com/job/google-999",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.country_code == "US"


def test_google_jobs_accepts_india_and_parses_city_state() -> None:
    scraper = _google_jobs_scraper()
    raw = {
        "title": "Senior Backend Engineer",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/google-12345",
        "companyName": "Acme",
        "descriptionText": "We need a Python and Django expert. ₹20-30 LPA.",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.location_city == "Bengaluru"
    assert rec.location_state == "Karnataka"
    assert rec.country_code == "IN"
    assert rec.apify_job_id == "gj_google-12345"
    assert rec.company_name == "Acme"
    assert "python" in rec.skills_required


def test_google_jobs_empty_title_is_skipped() -> None:
    scraper = _google_jobs_scraper()
    assert scraper.normalise({"location": "Mumbai, India"}) is None


def test_google_jobs_dedup_id_falls_back_to_namespaced_uuid_when_no_job_id() -> None:
    scraper = _google_jobs_scraper()
    rec = scraper.normalise(
        {"title": "Data Scientist", "location": "Pune, India", "jobUrl": "https://x.test/no-id"}
    )
    assert rec is not None
    assert rec.apify_job_id.startswith("gj_")
    uuid.UUID(rec.apify_job_id.removeprefix("gj_"))  # parses as a valid uuid


def test_google_jobs_uses_country_code_when_location_omits_country() -> None:
    scraper = _google_jobs_scraper()
    raw = {
        "title": "Category Planner",
        "location": "Bengaluru, Karnataka",
        "country": "in",
        "job_id": "country-1",
    }

    rec = scraper.normalise(raw)

    assert rec is not None
    assert rec.country_code == "IN"
    assert rec.location_city == "Bengaluru"


def test_google_jobs_rejects_unresolved_market() -> None:
    scraper = _google_jobs_scraper()
    raw = {
        "title": "Engineer",
        "location": "Nairobi, Kenya",
        "jobUrl": "https://jobs.google.com/job/google-1",
    }
    assert scraper.normalise(raw) is None


def test_parse_salary_lpa_range() -> None:
    scraper = _google_jobs_scraper()
    assert scraper._parse_salary("Compensation: ₹20-30 LPA") == (2_000_000, 3_000_000)
    assert scraper._parse_salary("no salary mentioned") == (None, None)


def test_extract_job_id_from_google_jobs_urls() -> None:
    scraper = _google_jobs_scraper()
    assert scraper._extract_job_id("https://jobs.google.com/job/google-4567") == "google-4567"
    assert scraper._extract_job_id("https://example.com/role") is None


# ── JobIngester._upsert_jobs accounting ───────────────────────────────────────


class _FakeConn:
    """Minimal async stand-in for asyncpg.Connection used by JobIngester."""

    def __init__(
        self,
        *,
        job_exists: bool = False,
        fail_execute: bool = False,
        apply_url_exists: bool = False,
    ) -> None:
        self.executes: list[str] = []
        self._job_exists = job_exists
        self._fail_execute = fail_execute
        self._apply_url_exists = apply_url_exists

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        flat = " ".join(query.split())
        if "FROM public.jobs WHERE apify_job_id" in flat:
            if self._job_exists:
                return {"id": uuid.uuid4(), "updated_at": datetime.now(UTC)}
            return None
        if "WHERE apply_url = $1" in flat:
            return {"id": uuid.uuid4()} if self._apply_url_exists else None
        return None

    async def execute(self, query: str, *args: object) -> str:
        if self._fail_execute:
            raise RuntimeError("simulated db failure")
        self.executes.append(" ".join(query.split()))
        return "OK"


def _record(job_id: str = "gj_1") -> JobRecord:
    return JobRecord(apify_job_id=job_id, title="Engineer", location_city="Pune")


def _ingester(conn: _FakeConn) -> JobIngester:
    return JobIngester(apify_token="test-token", db=conn)  # type: ignore[arg-type]


async def test_upsert_inserts_new_job() -> None:
    conn = _FakeConn(job_exists=False)
    inserted, updated, skipped = await _ingester(conn)._upsert_jobs([_record()])
    assert (inserted, updated, skipped) == (1, 0, 0)
    assert any("INSERT INTO public.jobs" in e for e in conn.executes)


async def test_upsert_updates_existing_job() -> None:
    conn = _FakeConn(job_exists=True)
    inserted, updated, skipped = await _ingester(conn)._upsert_jobs([_record()])
    assert (inserted, updated, skipped) == (0, 1, 0)
    assert any("UPDATE public.jobs SET" in e for e in conn.executes)


async def test_upsert_skips_on_db_error() -> None:
    conn = _FakeConn(job_exists=False, fail_execute=True)
    inserted, updated, skipped = await _ingester(conn)._upsert_jobs([_record()])
    assert (inserted, updated, skipped) == (0, 0, 1)


async def test_upsert_skips_cross_source_duplicate_by_apply_url() -> None:
    # Same posting under a new apify_job_id but an existing apply_url (a re-scrape
    # or another source) must not create a duplicate row.
    conn = _FakeConn(job_exists=False, apply_url_exists=True)
    rec = JobRecord(
        apify_job_id="gj_2",
        title="Engineer",
        location_city="Pune",
        apply_url="https://careers.example.com/job/123",
    )
    inserted, updated, skipped = await _ingester(conn)._upsert_jobs([rec])
    assert (inserted, updated, skipped) == (0, 0, 1)
    assert not any("INSERT INTO public.jobs" in e for e in conn.executes)


# ── career-path-scoped ingestion ──────────────────────────────────────────────


def test_derive_ingest_queries_prefers_target_titles() -> None:
    q = derive_ingest_queries(
        target_titles=["UX Lead", "Product Designer"],
        current_title="UX Designer",
        skills=["figma"],
    )
    assert q[0] == "UX Lead"  # career-path target leads
    assert "UX Designer" in q  # current title still included


def test_derive_ingest_queries_falls_back_to_skills_when_thin() -> None:
    q = derive_ingest_queries(
        target_titles=[], current_title=None, skills=["python", "react", "sql", "go"]
    )
    assert q == ["python", "react", "sql"]  # no titles → top 3 skills


def test_derive_ingest_queries_dedupes_and_caps() -> None:
    q = derive_ingest_queries(
        target_titles=["UX Lead", "ux lead", "A", "B", "C", "D", "E", "F"],
        current_title="UX Lead",
        skills=[],
        expand=False,  # isolate dedup/cap behaviour from adjacent-title expansion
        max_queries=6,
    )
    assert q == ["UX Lead", "A", "B", "C", "D", "E"]  # case-insensitive dedup + cap 6


def test_derive_ingest_queries_expands_niche_titles() -> None:
    # "Growth Designer" barely exists on Indian boards → expand to board-real
    # adjacent titles so the scrape still returns live openings.
    q = derive_ingest_queries(target_titles=["Growth Designer"], current_title=None, skills=[])
    assert q[0] == "Growth Designer"  # original intent leads
    assert "Product Designer" in q  # adjacent expansion
    assert "Growth Manager" in q


def test_derive_ingest_queries_expands_generalist_customer_success_titles() -> None:
    q = derive_ingest_queries(
        target_titles=["Assistant Manager"],
        current_title=None,
        skills=["Customer Success", "Customer Support", "Communication"],
    )

    assert q[0] == "Assistant Manager"
    assert "Customer Success Manager" in q
    assert "Customer Support Manager" in q
    assert "Operations Manager" in q


def test_derive_ingest_queries_expands_fashion_and_merchandising_profiles() -> None:
    q = derive_ingest_queries(
        target_titles=["Category Planner"],
        current_title=None,
        skills=["Fashion Buying", "Merchandising", "Retail Planning"],
    )

    assert q[0] == "Category Planner"
    assert "Category Manager" in q
    assert "Merchandiser" in q
    assert "Fashion Buyer" in q


def test_derive_ingest_queries_expands_go_to_market_titles_to_gtm_synonyms() -> None:
    q = derive_ingest_queries(
        target_titles=["Go-to-Market Lead"],
        current_title="GTM Lead - AI Resume Builder",
        skills=["B2B SaaS", "Sales", "Revenue"],
        max_queries=12,
    )

    assert q[0] == "Go-to-Market Lead"
    assert "GTM Lead" in q
    assert "Lead GTM" in q
    assert "Head of GTM" in q
    assert "GTM Manager" in q


def test_derive_ingest_queries_expands_founder_titles() -> None:
    q = derive_ingest_queries(
        target_titles=["Founder"],
        current_title="Co-Founder",
        skills=["Fundraising", "Product Strategy", "GTM"],
        max_queries=12,
    )

    assert q[0] == "Founder"
    assert "Co-Founder" in q
    assert "Entrepreneur in Residence" in q
    assert "Startup Founder" in q


def test_derive_ingest_locations_expands_brooklyn_to_new_york() -> None:
    locations = derive_ingest_locations(["Brooklyn"], None)

    assert locations[0] == "New York, New York, United States"
    assert "Brooklyn, New York, United States" in locations


def test_derive_ingest_locations_expands_market_city_to_country_context() -> None:
    assert derive_ingest_locations(["London"], None)[0] == "London, England, United Kingdom"
    assert derive_ingest_locations(["Bengaluru"], None)[0] == "Bengaluru, Karnataka, India"
    assert derive_ingest_locations(["Karnataka"], None)[0] == "Karnataka, India"
    assert derive_ingest_locations(["Maharashtra"], None)[0] == "Maharashtra, India"


def test_derive_ingest_queries_do_not_pollute_selected_data_path_with_operations_title() -> None:
    q = derive_ingest_queries(
        target_titles=["Data Analyst"],
        current_title="Operations Executive",
        skills=["SQL", "Excel", "Python", "Reporting"],
        max_queries=10,
    )

    assert q[0] == "Data Analyst"
    assert "Data Engineer" in q
    assert "Operations Executive" in q
    assert "Operations Manager" not in q
    assert "Program Manager" not in q


def test_derive_ingest_queries_do_not_pollute_selected_customer_success_path() -> None:
    q = derive_ingest_queries(
        target_titles=["Customer Success Manager"],
        current_title="Assistant Manager",
        skills=["Customer Support", "Communication", "Relationship Management"],
        max_queries=10,
    )

    assert q[0] == "Customer Success Manager"
    assert "Customer Success Associate" in q
    assert "Client Success Manager" in q
    assert "Assistant Manager" in q
    assert "Operations Manager" not in q


def test_derive_ingest_queries_contextualizes_bare_team_lead_targets() -> None:
    q = derive_ingest_queries(
        target_titles=["Team Lead"],
        current_title="Category Team Lead (Fastag)",
        skills=[
            "Customer Experience Management",
            "Customer Success",
            "CX Operations",
            "SLA Management",
            "KPI Management",
        ],
        max_queries=10,
    )

    assert "Team Lead" not in q
    assert "Customer Experience Manager" in q
    assert "Customer Success Manager" in q
    assert "CX Operations Manager" in q


def test_derive_ingest_queries_keeps_cx_operations_in_customer_success_lane() -> None:
    q = derive_ingest_queries(
        target_titles=["CX Operations Lead"],
        current_title="Category Team Lead (Fastag)",
        skills=["Customer Experience Management", "SLA Management", "KPI Management"],
        max_queries=10,
    )

    assert q[0] == "CX Operations Lead"
    assert "CX Operations Manager" in q
    assert "Customer Success Operations Manager" in q
    assert "Operations Manager" not in q
    assert "Program Manager" not in q


def test_derive_ingest_queries_uses_skill_domains_for_thin_titles() -> None:
    q = derive_ingest_queries(
        target_titles=[],
        current_title="Executive",
        skills=["Recruitment", "Payroll", "Employee Relations"],
    )

    assert q[0] == "Executive"
    assert "HR Executive" in q
    assert "Talent Acquisition Specialist" in q


async def test_ingest_for_candidate_scopes_to_career_path() -> None:
    class _Conn:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
            return {
                "current_title": "UX Designer",
                "location_city": "Bengaluru",
                "skills": ["figma"],
                "target_titles": ["Senior Product Designer", "UX Lead"],
                "target_locations": ["Bengaluru", "Remote"],
            }

    captured: dict = {}
    ing = JobIngester(apify_token="test-token", db=_Conn())  # type: ignore[arg-type]

    async def _fake_ingest(
        *,
        queries,
        locations,
        max_results_per_query,
        time_range,
        description_search=None,
    ):
        captured["queries"] = queries
        captured["locations"] = locations
        return {"inserted": 0}

    ing.ingest = _fake_ingest  # type: ignore[method-assign]
    await ing.ingest_for_candidate("11111111-1111-1111-1111-111111111111")

    assert captured["queries"][0] == "Senior Product Designer"  # career-path target leads
    assert "UX Lead" in captured["queries"]  # second target still present
    assert "UX Designer" in captured["queries"]  # current title still included
    assert "Product Designer" in captured["queries"]  # board-real adjacent expansion
    assert captured["locations"] == ["Bengaluru, Karnataka, India", "Remote"]


async def test_ingest_for_candidate_uses_candidate_intelligence_plan(monkeypatch) -> None:
    class _Conn:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
            return {
                "current_title": "Legacy Title",
                "location_city": "Mumbai",
                "skills": ["legacy"],
                "target_titles": ["Legacy Target"],
                "target_locations": ["Mumbai"],
            }

    async def _fake_load_candidate_intelligence(db: object, candidate_id: object) -> object:
        return {"candidate_id": str(candidate_id)}

    def _fake_build_plan(snapshot: object) -> CandidateJobIngestPlan:
        return CandidateJobIngestPlan(
            candidate_id="11111111-1111-1111-1111-111111111111",
            market="IN",
            remote_preference="remote_only",
            title_inputs=["Head of Growth", "Lifecycle Marketing Lead"],
            current_title="Senior Growth Manager",
            skills=["Lifecycle Marketing", "SQL"],
            raw_locations=["Remote", "Bengaluru"],
        )

    monkeypatch.setattr(
        job_ingester_module,
        "load_candidate_intelligence",
        _fake_load_candidate_intelligence,
        raising=False,
    )
    monkeypatch.setattr(
        job_ingester_module,
        "build_candidate_job_ingest_plan",
        _fake_build_plan,
        raising=False,
    )

    captured: dict = {}
    ing = JobIngester(apify_token="test-token", db=_Conn())  # type: ignore[arg-type]

    async def _fake_ingest(
        *,
        queries,
        locations,
        max_results_per_query,
        time_range,
        description_search=None,
    ):
        captured["queries"] = queries
        captured["locations"] = locations
        return {"inserted": 0}

    ing.ingest = _fake_ingest  # type: ignore[method-assign]
    await ing.ingest_for_candidate("11111111-1111-1111-1111-111111111111")

    assert captured["queries"][0] == "Head of Growth"
    assert "Lifecycle Marketing Lead" in captured["queries"]
    assert "Legacy Target" not in captured["queries"]
    assert captured["locations"] == ["Remote", "Bengaluru, Karnataka, India"]


async def test_ingest_uses_google_jobs_as_only_runtime_source() -> None:
    class _Conn:
        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            return []

    class _Scraper:
        async def scrape(self, **kwargs: object) -> tuple[list[dict], list[JobRecord], dict]:
            return (
                [{"title": "Customer Success Manager"}],
                [
                    JobRecord(
                        apify_job_id="gj_1",
                        title="Customer Success Manager",
                        country_code="IN",
                        source="google_jobs",
                    )
                ],
                {
                    "run_id": "run-1",
                    "dataset_id": "dataset-1",
                    "raw_items": 1,
                    "normalised": 1,
                },
            )

    ing = JobIngester(apify_token="test-token", db=_Conn())  # type: ignore[arg-type]
    ing._scraper = _Scraper()  # type: ignore[assignment]

    async def _fake_upsert(records: list[JobRecord]) -> tuple[int, int, int]:
        assert records[0].apify_job_id == "gj_1"
        return 1, 0, 0

    async def _fake_companies(records: list[JobRecord]) -> None:
        assert records[0].source == "google_jobs"

    ing._upsert_jobs = _fake_upsert  # type: ignore[method-assign]
    ing._ensure_companies = _fake_companies  # type: ignore[method-assign]

    stats = await ing.ingest(queries=["Customer Success Manager"], locations=["India"])

    assert set(stats["sources"]) == {"google_jobs"}
    assert stats["run_id"] == "run-1"
    assert stats["inserted"] == 1


# ── source health / fail-loud (Google Jobs only) ──────────────────────────────


def test_all_sources_failed_detection() -> None:
    from hireloop_api.services.apify.job_ingester import (
        _all_sources_failed,
        _source_errors,
    )

    ok = {"google_jobs": {"raw_items": 20, "normalised": 20}}
    one_bad = {
        "google_jobs": {"raw_items": 20, "normalised": 20},
        "legacy_source": {"error": "disabled", "raw_items": 0, "normalised": 0},
    }
    all_bad = {"google_jobs": {"error": "boom", "raw_items": 0, "normalised": 0}}

    # A healthy run is not "all failed"; a partial failure is degraded but usable.
    assert _all_sources_failed(ok) is False
    assert _all_sources_failed(one_bad) is False
    assert _source_errors(one_bad) == {"legacy_source": "disabled"}
    # Every attempted source down → must signal a hard failure (caller raises).
    assert _all_sources_failed(all_bad) is True
    assert _all_sources_failed({}) is False  # nothing attempted != failure
