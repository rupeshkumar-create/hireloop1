from hireloop_api.services.linkedin_oauth import (
    extract_linkedin_display_name,
    extract_linkedin_headline,
    headline_should_use_linkedin,
)


def test_extract_linkedin_headline_from_user_metadata() -> None:
    payload = {
        "user_metadata": {
            "full_name": "Rupesh Kumar",
            "headline": "Senior Software Engineer | Python & AWS",
        }
    }
    assert extract_linkedin_headline(payload) == "Senior Software Engineer | Python & AWS"


def test_extract_linkedin_headline_ignores_name_only_value() -> None:
    payload = {"user_metadata": {"full_name": "Rupesh Kumar", "headline": "Rupesh Kumar"}}
    assert extract_linkedin_headline(payload) is None


def test_headline_should_replace_when_stored_is_display_name() -> None:
    assert headline_should_use_linkedin(
        "Rupesh Kumar",
        display_name="Rupesh Kumar",
        user_full_name="Rupesh Kumar",
    )


def test_headline_should_not_replace_custom_headline() -> None:
    assert not headline_should_use_linkedin(
        "Staffing leader building AI hiring products",
        display_name="Rupesh Kumar",
        user_full_name="Rupesh Kumar",
    )


def test_extract_linkedin_display_name() -> None:
    payload = {"user_metadata": {"name": "Rupesh Kumar"}}
    assert extract_linkedin_display_name(payload) == "Rupesh Kumar"
