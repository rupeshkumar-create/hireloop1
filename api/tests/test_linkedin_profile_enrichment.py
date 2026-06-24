import inspect

from hireloop_api.routes.auth import bootstrap_user

# NOTE: The dedicated `hireloop_api.services.apify.linkedin_profile_scraper`
# module (ACTOR_ID / build_actor_input / map_profile_to_candidate_update) was
# intentionally removed. LinkedIn profile data is now sourced at OAuth time via
# `services.linkedin_oauth` + `services.linkedin_enrichment`, and bootstrap uses
# career-intelligence instead of a profile-scraper actor. The unit tests that
# exercised that removed module were dropped; the tests below assert the
# current (scraper-free) behaviour.


def test_bootstrap_does_not_schedule_linkedin_profile_scraper() -> None:
    source = inspect.getsource(bootstrap_user)

    assert "enrich_linkedin_profile_background" not in source
    assert "should_schedule_linkedin_enrichment" not in source
    assert "CAREER_INTELLIGENCE_UPDATE" in source
    assert "enqueue_job" in source


def test_should_schedule_returns_false_when_enrichment_disabled() -> None:
    from hireloop_api.config import Settings
    from hireloop_api.services.linkedin_enrichment import should_schedule_linkedin_enrichment

    # Enrichment is gated on `linkdapi_key`; an empty key means disabled.
    # Explicit init kwargs take priority over any .env value in pydantic-settings.
    settings = Settings(linkdapi_key="")
    schedule, url = should_schedule_linkedin_enrichment(
        linkedin_url="https://www.linkedin.com/in/testuser",
        linkedin_data={},
        settings=settings,
    )
    assert schedule is False
    assert url is None


def test_candidate_has_apify_profile_only_when_scrape_succeeded() -> None:
    from hireloop_api.services.linkedin_oauth import candidate_has_apify_profile

    assert not candidate_has_apify_profile({})
    assert not candidate_has_apify_profile({"user_metadata": {"headline": "PM"}})
    assert not candidate_has_apify_profile({"apify_scrape_status": "empty"})
    assert candidate_has_apify_profile({"apify_profile": {"name": "Ada"}})


def test_candidate_needs_extraction_after_empty_scrape() -> None:
    from hireloop_api.services.linkedin_oauth import candidate_needs_linkedin_extraction

    needs, url = candidate_needs_linkedin_extraction(
        linkedin_url="https://www.linkedin.com/in/testuser",
        linkedin_data={"apify_scrape_status": "empty"},
        force_retry=True,
    )
    assert needs is True
    assert url is not None

    needs_done, _ = candidate_needs_linkedin_extraction(
        linkedin_url="https://www.linkedin.com/in/testuser",
        linkedin_data={"apify_profile": {"name": "Ada"}},
    )
    assert needs_done is False


def test_extract_linkedin_profile_url_from_vanity() -> None:
    from hireloop_api.services.linkedin_oauth import extract_linkedin_profile_url

    url = extract_linkedin_profile_url({"user_metadata": {"preferred_username": "iamrupesh"}})
    assert url == "https://www.linkedin.com/in/iamrupesh"


def test_rejects_linkedin_oauth_placeholder_url() -> None:
    from hireloop_api.services.linkedin_oauth import (
        extract_linkedin_profile_url,
        is_valid_linkedin_profile_url,
    )

    assert not is_valid_linkedin_profile_url("https://www.linkedin.com/oauth")
    assert (
        extract_linkedin_profile_url(
            {
                "user_metadata": {
                    "profile": "https://www.linkedin.com/oauth",
                    "preferred_username": "iamrupesh",
                }
            }
        )
        == "https://www.linkedin.com/in/iamrupesh"
    )
