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


def test_saas_job_in_persona_pool() -> None:
    assert job_in_persona_pool(_job(), _cand()) is True


def test_weak_overall_not_persisted() -> None:
    assert (
        should_persist_match(
            _cand(),
            _job(),
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


def test_default_feed_floor_is_quality_first() -> None:
    assert DEFAULT_FEED_MIN_SCORE >= MIN_PERSIST_SCORE
