"""Tests for career path selection parsing."""

from hireloop_api.services.career_path_selection import (
    assistant_implied_option,
    career_path_options,
    extract_find_role_and_city,
    is_affirmative_reply,
    is_generic_job_search_reply,
    parse_career_path_selection,
)

OPTIONS = [
    "Senior Category Manager",
    "Head of Buying / Category Head - Fashion",
    "Director - Merchandising & Buying",
]

FASHION_OPTIONS = [
    "Senior Category Manager - Fashion",
    "Category Head - Apparel / Private Label",
    "AVP / Director - Category & Merchandising",
]


def test_parse_numeric_selection() -> None:
    assert parse_career_path_selection("2", OPTIONS) == OPTIONS[1]
    assert parse_career_path_selection("Yes, show me the Jobs. 2.", OPTIONS) == OPTIONS[1]


def test_parse_find_role_in_city() -> None:
    msg = (
        "Find Senior Category Manager - Fashion in Bengaluru for someone with "
        "12+ years of experience matching my skills in fashion buying."
    )
    assert parse_career_path_selection(msg, FASHION_OPTIONS) == FASHION_OPTIONS[0]
    role, city = extract_find_role_and_city(msg)
    assert role is not None
    assert "Senior Category Manager" in role
    assert city == "Bengaluru"


def test_parse_yes_do_it_after_assistant_search_offer() -> None:
    assistant = (
        "Now let me search for Category Head - Private Label / Apparel roles "
        "in Bengaluru at your 50 LPA target:"
    )
    assert (
        parse_career_path_selection(
            "Yes Do it",
            FASHION_OPTIONS,
            recent_assistant_message=assistant,
        )
        == FASHION_OPTIONS[1]
    )


def test_parse_yes_defaults_to_first_when_assistant_asked_pick_one() -> None:
    assistant = (
        "Which one should I search for first in Bengaluru? Pick one and "
        "I'll surface the live roles at 50 LPA."
    )
    assert is_affirmative_reply("Yes")
    assert (
        parse_career_path_selection(
            "Yes",
            FASHION_OPTIONS,
            recent_assistant_message=assistant,
        )
        == FASHION_OPTIONS[0]
    )


def test_parse_generic_find_jobs_defaults_to_first_after_picker() -> None:
    assistant = (
        "Which one should I search for first in Bengaluru? Pick one and "
        "I'll surface the live roles at 50 LPA."
    )
    assert is_generic_job_search_reply("Find me the Job.")
    assert (
        parse_career_path_selection(
            "Find me the Job.",
            FASHION_OPTIONS,
            recent_assistant_message=assistant,
        )
        == FASHION_OPTIONS[0]
    )


def test_assistant_implied_option_from_search_phrase() -> None:
    text = "Let me search for Senior Category Manager - Fashion in Bengaluru"
    assert assistant_implied_option(text, FASHION_OPTIONS) == FASHION_OPTIONS[0]


def test_parse_prioritize_chip_message() -> None:
    msg = (
        'I want to prioritize the "Head of Buying / Category Head - Fashion" '
        "career path. Show me matching jobs for this direction."
    )
    assert parse_career_path_selection(msg, OPTIONS) == OPTIONS[1]


def test_parse_prioritize_senior_category_manager_fashion() -> None:
    msg = (
        'I want to prioritize the "Senior Category Manager - Fashion" career path. '
        "Show me matching jobs for this direction."
    )
    options = ["Senior Category Manager - Fashion", "Head of Buying", "Director"]
    assert parse_career_path_selection(msg, options) == options[0]


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
