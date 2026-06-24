"""Tests for career path helpers."""

from hireloop_api.services.career_path import _profile_ready_for_path


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
