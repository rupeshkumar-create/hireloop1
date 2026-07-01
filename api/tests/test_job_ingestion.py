"""
Tests for the Apify job ingestion pipeline (P09).

These exercise the pure normalisation logic and the DB upsert path without
needing a real Apify token, network, or Postgres connection:

  * Multi-market normalisation (IN / US / GB) produces supported JobRecords.
  * Salary / location / skill / dedup-id parsing for both scrapers.
  * JobIngester._upsert_jobs insert / update / skip accounting via a fake conn.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from hireloop_api.services.apify.fantastic_jobs_scraper import ApifyFantasticJobsScraper
from hireloop_api.services.apify.job_ingester import JobIngester, derive_ingest_queries
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


# ── ApifyJobsScraper (LinkedIn) normalisation ─────────────────────────────────


def _linkedin_scraper() -> ApifyJobsScraper:
    return ApifyJobsScraper(api_token="test-token")


def test_linkedin_accepts_us_location() -> None:
    scraper = _linkedin_scraper()
    raw = {
        "title": "Senior Engineer",
        "location": "San Francisco, CA, USA",
        "jobUrl": "https://www.linkedin.com/jobs/view/999",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.country_code == "US"


def test_linkedin_accepts_india_and_parses_city_state() -> None:
    scraper = _linkedin_scraper()
    raw = {
        "title": "Senior Backend Engineer",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://www.linkedin.com/jobs/view/12345",
        "companyName": "Acme",
        "descriptionText": "We need a Python and Django expert. ₹20-30 LPA.",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.location_city == "Bengaluru"
    assert rec.location_state == "Karnataka"
    assert rec.country_code == "IN"
    assert rec.apify_job_id == "li_12345"
    assert rec.company_name == "Acme"
    assert "python" in rec.skills_required


def test_linkedin_empty_title_is_skipped() -> None:
    scraper = _linkedin_scraper()
    assert scraper.normalise({"location": "Mumbai, India"}) is None


def test_linkedin_dedup_id_falls_back_to_uuid_when_no_job_id() -> None:
    scraper = _linkedin_scraper()
    rec = scraper.normalise(
        {"title": "Data Scientist", "location": "Pune, India", "jobUrl": "https://x.test/no-id"}
    )
    assert rec is not None
    # Not a LinkedIn li_/numeric id → a uuid string was generated (non-empty).
    assert rec.apify_job_id
    assert not rec.apify_job_id.startswith("li_")
    uuid.UUID(rec.apify_job_id)  # parses as a valid uuid


def test_linkedin_rejects_unresolved_market() -> None:
    scraper = _linkedin_scraper()
    raw = {
        "title": "Engineer",
        "location": "Berlin, Germany",
        "jobUrl": "https://www.linkedin.com/jobs/view/1",
    }
    assert scraper.normalise(raw) is None


def test_parse_salary_lpa_range() -> None:
    scraper = _linkedin_scraper()
    assert scraper._parse_salary("Compensation: ₹20-30 LPA") == (2_000_000, 3_000_000)
    assert scraper._parse_salary("no salary mentioned") == (None, None)


def test_extract_job_id_from_linkedin_urls() -> None:
    scraper = _linkedin_scraper()
    assert scraper._extract_job_id("https://www.linkedin.com/jobs/view/4567") == "li_4567"
    assert scraper._extract_job_id("https://www.linkedin.com/jobs/?currentJobId=88") == "li_88"
    assert scraper._extract_job_id("https://example.com/role") is None


# ── ApifyFantasticJobsScraper normalisation ───────────────────────────────────


def _fantastic_scraper() -> ApifyFantasticJobsScraper:
    return ApifyFantasticJobsScraper(api_token="test-token", actor="fantastic/career")


def test_fantastic_accepts_us_country() -> None:
    scraper = _fantastic_scraper()
    raw = {
        "title": "Engineer",
        "countries_derived": ["United States"],
        "locations_derived": [{"city": "Austin", "country": "United States"}],
        "url": "https://careers.example.com/jobs/1",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.country_code == "US"


def test_fantastic_skips_when_no_country_info() -> None:
    scraper = _fantastic_scraper()
    raw = {"title": "Engineer", "countries_derived": [], "locations_derived": []}
    assert scraper.normalise(raw) is None


def test_fantastic_normalises_valid_india_job() -> None:
    scraper = _fantastic_scraper()
    raw = {
        "id": "abc123",
        "title": "Backend Engineer",
        "countries_derived": ["India"],
        "locations_derived": [{"city": "Hyderabad", "admin": "Telangana", "country": "India"}],
        "ai_salary_minvalue": 2_000_000,
        "ai_salary_maxvalue": 3_000_000,
        "ai_salary_currency": "INR",
        "ai_salary_unittext": "YEAR",
        "ai_work_arrangement": "Remote",
        "employment_type": ["Internship"],
        "ai_key_skills": ["Python", "FastAPI"],
        "organization": "Acme India",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.apify_job_id == "fj_abc123"
    assert rec.location_city == "Hyderabad"
    assert rec.country_code == "IN"
    assert rec.is_remote is True
    assert rec.employment_type == "internship"
    assert rec.ctc_min == 2_000_000
    assert rec.ctc_max == 3_000_000
    assert rec.skills_required == ["fastapi", "python"]  # sorted(set(...))
    assert rec.company_name == "Acme India"


def test_fantastic_drops_non_inr_salary() -> None:
    scraper = _fantastic_scraper()
    raw = {
        "id": "usd1",
        "title": "Engineer",
        "countries_derived": ["India"],
        "locations_derived": [{"city": "Mumbai", "country": "India"}],
        "ai_salary_minvalue": 100_000,
        "ai_salary_maxvalue": 150_000,
        "ai_salary_currency": "USD",
        "ai_salary_unittext": "YEAR",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.ctc_min is None
    assert rec.ctc_max is None


def test_fantastic_keeps_usd_salary_for_us_market() -> None:
    scraper = _fantastic_scraper()
    raw = {
        "id": "usd2",
        "title": "Engineer",
        "countries_derived": ["United States"],
        "locations_derived": [{"city": "Austin", "country": "United States"}],
        "ai_salary_minvalue": 100_000,
        "ai_salary_maxvalue": 150_000,
        "ai_salary_currency": "USD",
        "ai_salary_unittext": "YEAR",
        "url": "https://careers.example.com/jobs/us-2",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.country_code == "US"
    assert rec.ctc_min == 100_000
    assert rec.ctc_max == 150_000


def test_fantastic_apify_id_falls_back_to_url() -> None:
    scraper = _fantastic_scraper()
    raw = {
        "title": "Engineer",
        "countries_derived": ["India"],
        "locations_derived": [{"city": "Delhi", "country": "India"}],
        "url": "https://acme.com/careers/eng-42",
    }
    rec = scraper.normalise(raw)
    assert rec is not None
    assert rec.apify_job_id.startswith("fj_")


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


def _record(job_id: str = "li_1") -> JobRecord:
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
        apify_job_id="li_2",
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

    async def _fake_ingest(  # noqa: ANN001, ANN202
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
    assert captured["locations"] == ["Bengaluru", "Remote"]


# ── source health / fail-loud (HIR: fantastic-only + loud failures) ───────────


def test_all_sources_failed_detection() -> None:
    from hireloop_api.services.apify.job_ingester import (
        _all_sources_failed,
        _source_errors,
    )

    ok = {"fantastic_jobs": {"raw_items": 20, "normalised": 20}}
    one_bad = {
        "fantastic_jobs": {"raw_items": 20, "normalised": 20},
        "linkedin_jobs": {"error": "403 actor-is-not-rented", "raw_items": 0, "normalised": 0},
    }
    all_bad = {"fantastic_jobs": {"error": "boom", "raw_items": 0, "normalised": 0}}

    # A healthy run is not "all failed"; a partial failure is degraded but usable.
    assert _all_sources_failed(ok) is False
    assert _all_sources_failed(one_bad) is False
    assert _source_errors(one_bad) == {"linkedin_jobs": "403 actor-is-not-rented"}
    # Every attempted source down → must signal a hard failure (caller raises).
    assert _all_sources_failed(all_bad) is True
    assert _all_sources_failed({}) is False  # nothing attempted != failure
