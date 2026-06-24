"""#22: CV date normalization + interval-merged tenure math."""

from __future__ import annotations

from datetime import date

from hireloop_api.services.resume_parser import (
    WorkExperience,
    compute_tenure_years,
    parse_resume_date,
)


def test_parse_common_formats() -> None:
    assert parse_resume_date("Jan 2021") == date(2021, 1, 1)
    assert parse_resume_date("January, 2021") == date(2021, 1, 1)
    assert parse_resume_date("Mar'21") == date(2021, 3, 1)
    assert parse_resume_date("03/2021") == date(2021, 3, 1)
    assert parse_resume_date("2021-03") == date(2021, 3, 1)
    assert parse_resume_date("2021") == date(2021, 1, 1)


def test_present_words_and_garbage_return_none() -> None:
    for s in ("Present", "till date", "Current", "ongoing", None, "", "n/a", "soon"):
        assert parse_resume_date(s) is None


def test_tenure_simple_span() -> None:
    exp = [WorkExperience(start_date="Jan 2020", end_date="Jan 2023")]
    assert compute_tenure_years(exp) == 3


def test_tenure_merges_overlapping_roles() -> None:
    # Day job 2018-2022 + freelance 2020-2021 must NOT count as 5 years.
    exp = [
        WorkExperience(start_date="Jan 2018", end_date="Jan 2022"),
        WorkExperience(start_date="Jan 2020", end_date="Jan 2021"),
    ]
    assert compute_tenure_years(exp) == 4


def test_tenure_gap_not_counted() -> None:
    # 2 years + 1 year with a gap in between = 3, not the 5-year span.
    exp = [
        WorkExperience(start_date="Jan 2016", end_date="Jan 2018"),
        WorkExperience(start_date="Jan 2020", end_date="Jan 2021"),
    ]
    assert compute_tenure_years(exp) == 3


def test_present_role_counts_to_today() -> None:
    exp = [WorkExperience(start_date="Jan 2024", end_date="Present")]
    years = compute_tenure_years(exp)
    assert years is not None and years >= 2  # Jan 2024 → mid-2026


def test_undated_history_returns_none() -> None:
    assert compute_tenure_years([WorkExperience(title="Engineer")]) is None
    assert compute_tenure_years([]) is None
