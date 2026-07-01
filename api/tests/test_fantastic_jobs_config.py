"""Tests for Fantastic.jobs Apify actor input builder."""

from hireloop_api.config import Settings
from hireloop_api.services.apify.fantastic_jobs_config import (
    build_actor_input,
    description_search_for_candidate,
    fantastic_defaults_from_settings,
    merge_ingest_run_params,
)


def test_build_actor_input_includes_ai_filters() -> None:
    settings = Settings(
        fantastic_jobs_title_exclusions=["Intern:*"],
        fantastic_jobs_ai_languages=["English"],
        fantastic_jobs_exclude_ats_duplicate=True,
        fantastic_jobs_populate_ai_remote=True,
    )
    params = merge_ingest_run_params(
        settings,
        title_search=["Software Engineer"],
        location_search=["Bengaluru, Karnataka, India"],
        limit=500,
        time_range="24h",
        description_search=["Python:*"],
    )
    payload = build_actor_input(params)

    assert payload["timeRange"] == "24h"
    assert payload["limit"] == 500
    assert payload["removeAgency"] is True
    assert payload["excludeATSDuplicate"] is True
    assert payload["populateAiRemoteLocation"] is True
    assert payload["populateAiRemoteLocationDerived"] is True
    assert payload["descriptionType"] == "text"
    assert payload["titleSearch"] == ["Software Engineer"]
    assert payload["titleExclusionSearch"] == ["Intern:*"]
    assert payload["locationSearch"] == ["Bengaluru, Karnataka, India"]
    assert payload["descriptionSearch"] == ["Python:*"]
    assert payload["aiLanguageFilter"] == ["English"]
    assert "includeLinkedIn" not in payload
    assert "descriptionFormat" not in payload


def test_build_actor_input_omits_empty_optional_filters() -> None:
    payload = build_actor_input(fantastic_defaults_from_settings(None))
    assert "aiWorkArrangementFilter" not in payload
    assert "hasSalary" not in payload
    assert payload["locationSearch"] == ["India"]


def test_require_salary_and_visa_flags() -> None:
    settings = Settings(
        fantastic_jobs_require_salary=True,
        fantastic_jobs_visa_sponsorship_only=True,
    )
    payload = build_actor_input(fantastic_defaults_from_settings(settings))
    assert payload["hasSalary"] is True
    assert payload["aiVisaSponsorshipFilter"] is True


def test_description_search_for_candidate_prefixes_skills() -> None:
    settings = Settings(fantastic_jobs_max_description_search_terms=2)
    terms = description_search_for_candidate(["Python", "PostgreSQL", "Kafka"], settings)
    assert terms == ["Python:*", "PostgreSQL:*"]
