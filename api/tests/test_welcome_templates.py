"""Tests for role-specific welcome email templates."""

from __future__ import annotations

from hireloop_api.services.email.welcome_templates import render_welcome_email


def test_candidate_welcome_mentions_aarya() -> None:
    subject, html = render_welcome_email(
        role="candidate",
        full_name="Rupesh",
        app_base_url="https://app.hireschema.com",
    )
    assert "Aarya" in subject
    assert "Aarya" in html
    assert "/dashboard" in html
    assert "Talk to Aarya" in html


def test_recruiter_welcome_mentions_nitya() -> None:
    subject, html = render_welcome_email(
        role="recruiter",
        full_name="Priya",
        app_base_url="https://app.hireschema.com",
    )
    assert "Nitya" in subject
    assert "Nitya" in html
    assert "/recruiter" in html
    assert "recruiter dashboard" in html.lower()


def test_non_recruiter_role_uses_candidate_template() -> None:
    subject, html = render_welcome_email(
        role="candidate",
        full_name=None,
        app_base_url="https://app.hireschema.com",
    )
    assert "Aarya" in subject
    assert "there" in html
