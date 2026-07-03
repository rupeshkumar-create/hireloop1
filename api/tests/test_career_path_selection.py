"""Tests for career path selection parsing."""

from hireloop_api.services.career_path_selection import (
    career_path_options,
    parse_career_path_selection,
)

OPTIONS = [
    "Senior Category Manager",
    "Head of Buying / Category Head - Fashion",
    "Director - Merchandising & Buying",
]


def test_parse_numeric_selection() -> None:
    assert parse_career_path_selection("2", OPTIONS) == OPTIONS[1]
    assert parse_career_path_selection("Yes, show me the Jobs. 2.", OPTIONS) == OPTIONS[1]


def test_parse_prioritize_chip_message() -> None:
    msg = (
        'I want to prioritize the "Head of Buying / Category Head - Fashion" '
        "career path. Show me matching jobs for this direction."
    )
    assert parse_career_path_selection(msg, OPTIONS) == OPTIONS[1]


def test_parse_title_substring() -> None:
    assert (
        parse_career_path_selection("Head of Buying please", OPTIONS) == OPTIONS[1]
    )


def test_career_path_options_from_steps() -> None:
    path = {
        "steps": [
            {"title": "Current", "level": "current"},
            {"title": "Next Role", "level": "next"},
            {"title": "Future Role", "level": "future"},
        ],
        "target_titles": ["Fallback"],
    }
    assert career_path_options(path) == ["Next Role", "Future Role"]
