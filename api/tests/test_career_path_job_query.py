"""Unit tests for job-search query resolution helpers."""

from hireloop_api.services.career_path_selection import (
    default_prioritize_title,
    resolve_job_search_query,
)


def test_default_prioritize_title_prefers_next_step() -> None:
    path = {
        "prioritized_title": None,
        "steps": [
            {"title": "PM", "level": "current"},
            {"title": "Head of Product", "level": "next"},
        ],
        "target_titles": ["Director Product"],
    }
    assert default_prioritize_title(path) == "Head of Product"


def test_resolve_job_search_query_generic_find_jobs_uses_path() -> None:
    path = {
        "target_titles": ["Senior Backend Engineer"],
        "steps": [],
    }
    q = resolve_job_search_query(
        "Find me the best matching jobs for my profile",
        user_intent="job_search",
        career_path=path,
        prioritized_title=None,
        just_prioritized=None,
        current_title="Software Engineer",
    )
    assert q == "Senior Backend Engineer"


def test_resolve_job_search_query_skips_non_job_intent() -> None:
    q = resolve_job_search_query(
        "Help me improve my resume",
        user_intent="profile_improvement",
        career_path=None,
        prioritized_title=None,
        just_prioritized=None,
    )
    assert q is None
