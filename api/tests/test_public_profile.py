from hireloop_api.services.public_profile import (
    _redact_public_fields,
    slug_needs_anonymization,
)


def test_slug_needs_anonymization_when_contact_hidden() -> None:
    assert slug_needs_anonymization("contact-vivek-kumar-a5d2b8", hide_contact=True)
    assert not slug_needs_anonymization("c-deadbeefcafe", hide_contact=True)
    assert not slug_needs_anonymization("contact-vivek-kumar", hide_contact=False)


def test_redact_public_fields_hides_identity() -> None:
    cand = {
        "headline": "Category Planner at Target",
        "summary": "Retail merchandising background.",
        "current_title": "Category Planner",
        "current_company": "Target",
        "years_experience": 12,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "looking_for": "Senior Category Manager",
        "linkedin_url": "https://linkedin.com/in/example",
        "email": "test@example.com",
        "phone": "+911234567890",
    }
    out = _redact_public_fields(
        cand,
        hide_contact=True,
        display_name="Vivek Kumar",
    )
    assert out["display_name"] is None
    assert out["location_city"] is None
    assert out["location_state"] is None
    assert out["linkedin_url"] is None
    assert out["contact"]["hidden"] is True
    assert out["contact"]["email"] is None
    assert out["contact"]["phone"] is None
    assert out["headline"] == "Category Planner at Target"
    assert out["current_title"] == "Category Planner"


def test_redact_public_fields_shows_contact_when_allowed() -> None:
    cand = {
        "headline": "Engineer",
        "summary": None,
        "current_title": "Engineer",
        "current_company": "Acme",
        "years_experience": 5,
        "location_city": "Mumbai",
        "location_state": "Maharashtra",
        "looking_for": None,
        "linkedin_url": "https://linkedin.com/in/acme",
        "email": "open@example.com",
        "phone": "+911111111111",
    }
    out = _redact_public_fields(
        cand,
        hide_contact=False,
        display_name="Ada Lovelace",
    )
    assert out["display_name"] == "Ada Lovelace"
    assert out["location_city"] == "Mumbai"
    assert out["contact"]["email"] == "open@example.com"
