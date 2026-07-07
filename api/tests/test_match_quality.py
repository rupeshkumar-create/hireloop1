"""Tests for match quality verification gates."""

from __future__ import annotations

from hireloop_api.services.match_quality import (
    DEFAULT_FEED_MIN_SCORE,
    MIN_PERSIST_SCORE,
    job_in_persona_pool,
    should_persist_match,
)


def _cand(**kwargs: object) -> dict:
    base = {
        "current_title": "Go-To-Market Lead",
        "current_company": "Candidately",
        "headline": "B2B SaaS staffing",
        "skills": ["AI", "Sales", "Automation"],
        "target_titles": ["Head of Sales", "VP Sales"],
    }
    base.update(kwargs)
    return base


def _job(**kwargs: object) -> dict:
    base = {
        "title": "Head of Sales",
        "company_name": "Acme SaaS",
        "description": "B2B software sales",
        "skills_required": ["sales", "saas"],
    }
    base.update(kwargs)
    return base


def test_hospitality_job_excluded_from_saas_persona_pool() -> None:
    cand = _cand()
    hotel = _job(
        title="Associate Director of Sales",
        company_name="AccorHotel",
        description="hotel hospitality resort",
        skills_required=["sales", "hospitality"],
    )
    assert job_in_persona_pool(hotel, cand) is False


def test_dental_clinic_sales_job_excluded_from_staffing_saas_persona_pool() -> None:
    dental = _job(
        title="Sales Manager",
        company_name="SmileBright Dental Clinic",
        description="dental clinic healthcare practice growth and patient acquisition",
        skills_required=["sales", "patient acquisition"],
    )
    assert job_in_persona_pool(dental, _cand()) is False


def test_saas_job_in_persona_pool() -> None:
    assert job_in_persona_pool(_job(), _cand()) is True


def test_weak_overall_persists_when_path_aligned() -> None:
    # 0.30 vs the exact role family the candidate chose: a skill-sparse fresh
    # profile can't clear 0.35 (skill overlap 0 kills the 0.40-weight dim),
    # and dropping it erased every real on-path job ("only demo jobs" bug).
    assert (
        should_persist_match(
            _cand(),
            _job(),
            {"overall": MIN_PERSIST_SCORE - 0.05},
        )
        is True
    )


def test_very_weak_overall_not_persisted_even_when_aligned() -> None:
    assert (
        should_persist_match(
            _cand(),
            _job(),
            {"overall": 0.15},
        )
        is False
    )


def test_weak_overall_not_persisted_when_off_path() -> None:
    off_path = _job(
        title="Staff Accountant",
        company_name="Ledger LLP",
        description="bookkeeping and monthly close",
        skills_required=["accounting", "tally"],
    )
    assert (
        should_persist_match(
            _cand(),
            off_path,
            {"overall": MIN_PERSIST_SCORE - 0.05},
        )
        is False
    )


def test_hospitality_match_not_persisted_even_if_score_inflated() -> None:
    hotel = _job(
        title="Hotel Sales Manager",
        company_name="Marriott",
        description="hospitality hotel",
        skills_required=["sales"],
    )
    assert (
        should_persist_match(
            _cand(),
            hotel,
            {"overall": 0.55},
        )
        is False
    )


def test_dental_clinic_match_not_persisted_even_if_sales_score_is_inflated() -> None:
    dental = _job(
        title="Sales Manager",
        company_name="SmileBright Dental Clinic",
        description="dental clinic healthcare practice growth and patient acquisition",
        skills_required=["sales"],
    )
    assert (
        should_persist_match(
            _cand(),
            dental,
            {"overall": 0.65},
        )
        is False
    )


def test_default_feed_floor_is_quality_first() -> None:
    assert DEFAULT_FEED_MIN_SCORE >= MIN_PERSIST_SCORE


def test_hireloop_test_job_bypasses_quality_gates() -> None:
    from hireloop_api.services.test_jobs import TEST_COMPANY_NAME

    cand = _cand(current_title="Data Analyst", skills=["sql"])
    test_job = _job(
        title="Category Planner — Apparel",
        company_name=TEST_COMPANY_NAME,
        description="fashion retail",
        skills_required=["merchandising"],
    )
    assert job_in_persona_pool(test_job, cand) is True
    assert should_persist_match(cand, test_job, {"overall": 0.1}) is True
