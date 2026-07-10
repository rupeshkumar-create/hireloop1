from hireloop_api.services.email.notification_templates import (
    normalize_category,
    render_notification_email,
)
from hireloop_api.services.notifications import _pref_channel_allowed


def test_normalize_category_aliases() -> None:
    assert normalize_category("job_match") == "job_match_alerts"
    assert normalize_category("intro_status") == "intro_updates"


def test_render_job_match_single() -> None:
    subject, html = render_notification_email(
        "job_match_alerts",
        {
            "full_name": "Priya",
            "job_title": "PM",
            "company_name": "Acme",
            "score_pct": 82,
            "cta_url": "https://www.hireschema.com/dashboard",
        },
    )
    assert "PM" in subject
    assert "Priya" in html
    assert "82%" in html


def test_pref_defaults_opt_in() -> None:
    assert _pref_channel_allowed({}, "job_match_alerts", "email") is True
    assert (
        _pref_channel_allowed({"job_match_alerts": {"email": False}}, "job_match_alerts", "email")
        is False
    )
