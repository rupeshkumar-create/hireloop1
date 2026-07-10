"""#35: shared title taxonomy — synonyms and shorthand must match."""

from __future__ import annotations

from hireloop_api.services.titles import canonical_title_tokens, title_affinity


def test_synonym_titles_are_perfect_match() -> None:
    assert title_affinity("Backend Developer", "Backend Engineer") >= 0.9
    assert title_affinity("Software Programmer", "Software Engineer") >= 0.9


def test_indian_shorthand_expands() -> None:
    assert title_affinity("SDE II", "Software Engineer") >= 0.65
    aff = title_affinity("Senior PM", "Product Manager")
    assert aff is not None and aff >= 0.65
    aff = title_affinity("SDET", "QA Engineer")
    assert aff is not None and aff >= 0.34


def test_seniority_affects_score() -> None:
    aff = title_affinity("Junior Data Analyst", "Lead Data Analyst")
    assert aff is not None and aff >= 0.7
    intern_principal = title_affinity("Intern Software Engineer", "Principal Software Engineer")
    assert intern_principal is not None and intern_principal < 0.9


def test_team_lead_words_are_not_role_function_signal() -> None:
    assert canonical_title_tokens("Team Lead") == frozenset()
    assert canonical_title_tokens("Customer Success Team Lead") == frozenset(
        {"customer", "success"}
    )


def test_unrelated_roles_score_low() -> None:
    aff = title_affinity("Sales Executive", "Backend Engineer")
    assert aff is not None and aff < 0.35


def test_unknown_returns_none() -> None:
    assert title_affinity(None, "Engineer") is None
    assert title_affinity("", "") is None
