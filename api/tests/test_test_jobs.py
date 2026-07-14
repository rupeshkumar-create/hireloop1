"""Tests for global test-job visibility (rupesh.kumar@candidate.ly roles)."""

from __future__ import annotations

from hireloop_api.config import Settings
from hireloop_api.services import test_jobs
from hireloop_api.services.match_quality import job_in_persona_pool, should_persist_match
from hireloop_api.services.test_jobs import (
    TEST_COMPANY_NAME,
    TEST_MATCH_SCORE,
    append_test_jobs,
    is_test_job,
    prepend_test_jobs,
)
from hireloop_api.services.test_jobs import (
    test_jobs_enabled as _test_jobs_enabled,
)


def test_is_test_job_by_company_name() -> None:
    assert is_test_job({"company_name": TEST_COMPANY_NAME}) is True


def test_is_test_job_by_legacy_hireloop_name() -> None:
    assert is_test_job({"company_name": "Hireloop Test Co"}) is True


def test_is_test_job_by_recruiter_email() -> None:
    assert is_test_job({"recruiter_email": "rupesh.kumar@candidate.ly"}) is True


def test_regular_job_is_not_test_job() -> None:
    assert is_test_job({"company_name": "Acme Corp"}) is False


def test_test_job_bypasses_persona_pool() -> None:
    cand = {
        "current_title": "UX Designer",
        "skills": ["figma"],
        "target_titles": ["Product Designer"],
    }
    test_job = {
        "title": "Category Planner — Apparel",
        "company_name": TEST_COMPANY_NAME,
        "description": "fashion retail",
        "skills_required": ["merchandising"],
    }
    assert job_in_persona_pool(test_job, cand) is True


def test_test_job_always_persisted() -> None:
    cand = {"current_title": "UX Designer", "skills": ["figma"]}
    test_job = {
        "title": "Go-To-Market Lead",
        "company_name": TEST_COMPANY_NAME,
        "skills_required": ["sales"],
    }
    assert should_persist_match(cand, test_job, {"overall": 0.1}) is True


def test_append_test_jobs_puts_demo_roles_after_market_matches() -> None:
    regular = [{"job_id": "a", "title": "Growth Manager"}]
    test = [{"job_id": "b", "title": "Demo Role"}]
    merged = append_test_jobs(regular, test, limit=5)
    assert merged[0]["job_id"] == "a"
    assert merged[-1]["job_id"] == "b"


def test_prepend_test_jobs_keeps_test_roles_first() -> None:
    regular = [{"job_id": "aaa", "title": "Other"}]
    test = [{"job_id": "bbb", "title": "Test Role", "overall_score": TEST_MATCH_SCORE}]
    merged = prepend_test_jobs(regular, test, limit=5)
    assert merged[0]["job_id"] == "bbb"
    assert len(merged) == 2


def test_test_jobs_disabled_in_production() -> None:
    # Production Settings enforce strong secrets — provide dummies so the
    # test doesn't depend on the local .env (CI has none).
    settings = Settings(
        environment="production",
        secret_key="x" * 40,
        service_secret="y" * 40,
    )
    assert _test_jobs_enabled(settings) is False


def test_test_jobs_enabled_in_development() -> None:
    settings = Settings(environment="development")
    assert _test_jobs_enabled(settings) is True


def test_production_company_exclusion_keeps_rows_with_nullable_company_fields(
    monkeypatch,
) -> None:
    monkeypatch.setattr(test_jobs, "test_jobs_enabled", lambda settings=None: False)

    clause = test_jobs.test_jobs_company_sql_exclude(company_alias="co")

    assert "COALESCE(co.domain, '')" in clause
    assert "COALESCE(co.name, '')" in clause


def test_production_full_exclusion_is_null_safe(monkeypatch) -> None:
    monkeypatch.setattr(test_jobs, "test_jobs_enabled", lambda settings=None: False)

    clause = test_jobs.test_jobs_sql_exclude(company_alias="co", user_alias="u")

    assert "COALESCE(co.domain, '')" in clause
    assert "COALESCE(co.name, '')" in clause
    assert "COALESCE(u.email, '')" in clause
