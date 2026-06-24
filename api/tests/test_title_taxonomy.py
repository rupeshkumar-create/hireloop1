"""#35: shared title taxonomy — synonyms and shorthand must match."""

from __future__ import annotations

from hireloop_api.services.titles import canonical_title_tokens, title_affinity


def test_synonym_titles_are_perfect_match() -> None:
    assert title_affinity("Backend Developer", "Backend Engineer") == 1.0
    assert title_affinity("Software Programmer", "Software Engineer") == 1.0


def test_indian_shorthand_expands() -> None:
    assert title_affinity("SDE II", "Software Engineer") == 1.0
    assert title_affinity("Senior PM", "Product Manager") == 1.0
    aff = title_affinity("SDET", "QA Engineer")
    assert aff is not None and aff >= 0.5


def test_seniority_words_ignored() -> None:
    assert canonical_title_tokens("Senior Staff Engineer III") == frozenset({"engineer"})
    assert title_affinity("Junior Data Analyst", "Lead Data Analyst") == 1.0


def test_unrelated_roles_score_low() -> None:
    aff = title_affinity("Sales Executive", "Backend Engineer")
    assert aff is not None and aff < 0.2


def test_unknown_returns_none() -> None:
    assert title_affinity(None, "Engineer") is None
    assert title_affinity("", "") is None
