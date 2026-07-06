import uuid

from hireloop_api.services.public_profile import (
    _redact_public_fields,
    slug_needs_anonymization,
)
from hireloop_api.services.public_profile_intelligence import (
    scrub_profile_for_privacy,
    _strip_headline_company,
)


def test_slug_needs_anonymization_when_contact_hidden() -> None:
    assert slug_needs_anonymization("contact-vivek-kumar-a5d2b8", hide_contact=True)
    assert not slug_needs_anonymization("c-deadbeef", hide_contact=True)
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
        owner_user_id=uuid.uuid4(),
    )
    assert out["display_name"] is None
    assert out["current_company"] is None
    assert out["privacy_mode"] is True
    assert out["location_city"] is None
    assert out["contact"]["hidden"] is True


def test_strip_headline_company() -> None:
    assert _strip_headline_company("PM at Acme Corp") == "PM"
    assert _strip_headline_company("Engineer") == "Engineer"


def test_scrub_profile_for_privacy_removes_employers() -> None:
    fields = {
        "headline": "Lead at Candidately",
        "summary": "Built products at Candidately for 4 years.",
        "current_title": "Lead",
        "current_company": "Candidately",
    }
    experience = [
        {
            "title": "Lead",
            "company": "Candidately",
            "description": "Shipped at Candidately.",
        }
    ]
    scrubbed, exp = scrub_profile_for_privacy(fields, experience, hide_contact=True)
    assert scrubbed["current_company"] is None
    assert scrubbed["headline"] == "Lead"
    assert "Candidately" not in (scrubbed["summary"] or "")
    assert exp[0]["company"] is None
    assert "Candidately" not in (exp[0]["description"] or "")


def test_redact_public_fields_shows_contact_when_authenticated() -> None:
    owner_id = uuid.uuid4()
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
        viewer={"id": str(uuid.uuid4())},
        owner_user_id=owner_id,
    )
    assert out["display_name"] == "Ada Lovelace"
    assert out["current_company"] == "Acme"
    assert out["contact"]["email"] == "open@example.com"
    assert out["viewer_authenticated"] is True


def test_redact_public_fields_hides_contact_for_anonymous() -> None:
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
        viewer=None,
        owner_user_id=uuid.uuid4(),
    )
    assert out["display_name"] == "Ada Lovelace"
    assert out["linkedin_url"] is None
    assert out["contact"]["email"] is None
    assert out["contact"]["requires_registration"] is True
    assert out["viewer_authenticated"] is False
