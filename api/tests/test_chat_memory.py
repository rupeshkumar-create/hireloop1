"""Tests for chat session helpers."""

from hireloop_api.services.job_preferences import extract_negative_preferences
from hireloop_api.services.memory import _build_brief


def test_build_brief_includes_prior_memory() -> None:
    text = _build_brief(
        {"current_title": "PM", "skills": []},
        "Prefers remote roles in Bengaluru.",
        [{"role": "user", "content": "Show me jobs"}],
    )
    assert "Prefers remote" in text
    assert "RUNNING MEMORY" in text


def test_negative_preferences_merge_shape() -> None:
    state = {"negative_preferences": {"companies": ["Acme Corp"]}}
    companies, titles = extract_negative_preferences(state)
    assert "acme corp" in companies
    assert titles == frozenset()
