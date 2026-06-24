"""#37: negative preferences — store + hard-filter "not interested" jobs."""

from __future__ import annotations

from hireloop_api.services.job_preferences import (
    apply_negative_preference,
    extract_negative_preferences,
)
from hireloop_api.services.ranking import HardConstraints, passes_hard_constraints


def test_apply_and_extract_roundtrip() -> None:
    state = apply_negative_preference({}, kind="companies", value="Acme")
    state = apply_negative_preference(state, kind="titles", value="Sales")
    companies, titles = extract_negative_preferences(state)
    assert "acme" in companies
    assert "sales" in titles


def test_apply_is_idempotent_and_case_insensitive() -> None:
    state = apply_negative_preference({}, kind="companies", value="Acme")
    state = apply_negative_preference(state, kind="companies", value="acme")
    companies, _ = extract_negative_preferences(state)
    assert len(companies) == 1


def test_remove() -> None:
    state = apply_negative_preference({}, kind="companies", value="Acme")
    state = apply_negative_preference(state, kind="companies", value="Acme", remove=True)
    companies, _ = extract_negative_preferences(state)
    assert "acme" not in companies


def test_extract_handles_json_string_and_missing() -> None:
    assert extract_negative_preferences(None) == (frozenset(), frozenset())
    assert extract_negative_preferences('{"negative_preferences": {"companies": ["X"]}}') == (
        frozenset({"x"}),
        frozenset(),
    )


def test_hard_filter_drops_excluded_company() -> None:
    c = HardConstraints(excluded_companies=frozenset({"acme"}))
    assert passes_hard_constraints({"company_name": "Acme", "title": "Engineer"}, c) is False
    assert passes_hard_constraints({"company_name": "Beta", "title": "Engineer"}, c) is True


def test_hard_filter_drops_excluded_title_keyword() -> None:
    c = HardConstraints(excluded_titles=frozenset({"sales"}))
    assert (
        passes_hard_constraints({"company_name": "Beta", "title": "Area Sales Manager"}, c) is False
    )
    assert passes_hard_constraints({"company_name": "Beta", "title": "Backend Engineer"}, c) is True
