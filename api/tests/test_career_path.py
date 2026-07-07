"""Tests for career path helpers."""

from hireloop_api.services.career_path import (
    _build_profile_brief,
    _profile_ready_for_path,
    build_career_path_system_prompt,
)


def test_profile_ready_with_current_title() -> None:
    assert _profile_ready_for_path({"current_title": "Software Engineer"}) is True


def test_profile_ready_with_skills() -> None:
    assert _profile_ready_for_path({"skills": ["Python"]}) is True


def test_profile_ready_with_real_headline() -> None:
    assert _profile_ready_for_path({"headline": "Backend engineer at Acme"}) is True


def test_profile_not_ready_for_placeholder_headline() -> None:
    assert _profile_ready_for_path({"headline": "New candidate"}) is False


def test_profile_not_ready_when_empty() -> None:
    assert _profile_ready_for_path({}) is False


def test_career_path_prompt_is_market_aware_for_us_candidates() -> None:
    prompt = build_career_path_system_prompt("US")

    assert "United States" in prompt
    assert "Indian job market" not in prompt
    assert "US job-board titles" in prompt


def test_career_path_prompt_is_market_aware_for_uk_candidates() -> None:
    prompt = build_career_path_system_prompt("GB")

    assert "United Kingdom" in prompt
    assert "Indian professionals" not in prompt
    assert "UK job-board titles" in prompt


def test_profile_brief_includes_market_and_full_location() -> None:
    brief = _build_profile_brief(
        {
            "full_name": "Candidate",
            "market": "GB",
            "current_title": "Data Analyst",
            "current_company": "Acme",
            "years_experience": 4,
            "location_city": "London",
            "location_state": "England",
            "skills": ["SQL"],
        }
    )

    assert "Market: GB" in brief
    assert "Location: London, England" in brief
