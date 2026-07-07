"""Tests for tailored resume opt-in setting."""

from __future__ import annotations

from hireloop_api.services.tailored_resume_settings import tailored_resume_enabled


def test_tailored_resume_disabled_by_default() -> None:
    assert tailored_resume_enabled({}) is False
    assert tailored_resume_enabled({"tailored_resume_enabled": False}) is False


def test_tailored_resume_enabled_when_opted_in() -> None:
    assert tailored_resume_enabled({"tailored_resume_enabled": True}) is True
