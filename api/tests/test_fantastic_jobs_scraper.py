"""Tests for Fantastic.jobs Apify normaliser (2026 field migration)."""

from hireloop_api.services.apify.fantastic_jobs_scraper import ApifyFantasticJobsScraper


def _scraper() -> ApifyFantasticJobsScraper:
    return ApifyFantasticJobsScraper("token", actor="fantastic-jobs/career-site-job-listing-api")


def test_normalise_new_salary_and_remote_fields() -> None:
    raw = {
        "id": "job-1",
        "title": "Senior Backend Engineer",
        "countries_derived": ["India"],
        "locations_derived": [{"country": "India", "city": "Bengaluru", "admin": "Karnataka"}],
        "ai_work_arrangement": "Remote OK",
        "ai_salary_min_value": 2500000,
        "ai_salary_max_value": 4000000,
        "ai_salary_currency": "INR",
        "ai_salary_unit_text": "YEAR",
        "ai_key_skills": ["Python", "PostgreSQL"],
        "organization": "Acme India",
        "org_linkedin_url": "https://linkedin.com/company/acme",
        "url": "https://example.com/jobs/1",
        "description_text": "Build APIs with Python",
        "date_valid_through": "2026-12-31T00:00:00Z",
    }
    rec = _scraper().normalise(raw)
    assert rec is not None
    assert rec.is_remote is True
    assert rec.ctc_min == 2500000
    assert rec.ctc_max == 4000000
    assert rec.company_name == "Acme India"
    assert rec.company_linkedin_url == "https://linkedin.com/company/acme"
    assert "python" in rec.skills_required


def test_normalise_legacy_field_fallbacks() -> None:
    raw = {
        "id": "job-2",
        "title": "Product Manager",
        "countries_derived": ["in"],
        "locations_derived": [{"country": "IN", "city": "Mumbai"}],
        "ai_salary_minvalue": 1800000,
        "ai_salary_maxvalue": 2200000,
        "ai_salary_currency": "inr",
        "ai_salary_unittext": "year",
        "ai_work_arrangement": "Hybrid",
        "organization": "Beta Corp",
        "linkedin_org_url": "https://linkedin.com/company/beta",
        "url": "https://example.com/jobs/2",
        "description_text": "Own the roadmap",
        "date_validthrough": "2026-11-30T00:00:00Z",
    }
    rec = _scraper().normalise(raw)
    assert rec is not None
    assert rec.is_remote is False
    assert rec.ctc_min == 1800000
    assert rec.company_linkedin_url == "https://linkedin.com/company/beta"


def test_normalise_skips_non_india() -> None:
    raw = {
        "id": "job-3",
        "title": "Engineer",
        "countries_derived": ["United States"],
        "url": "https://example.com/jobs/3",
    }
    assert _scraper().normalise(raw) is None
