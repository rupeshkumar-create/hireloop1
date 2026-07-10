"""Branded lifecycle HTML email templates and send helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from hireloop_api.config import Settings
from hireloop_api.services.email.brand_email import brand_shell, logo_url
from hireloop_api.services.email.lifecycle_emails import send_first_job_found_email
from hireloop_api.services.email.lifecycle_templates import (
    render_first_job_found_email,
    render_intro_requested_candidate_email,
    render_recruiter_approach_candidate_email,
    render_recruiter_intro_request_email,
    render_welcome_email,
)


def test_logo_url_uses_app_base() -> None:
    assert logo_url("https://www.hireschema.com") == (
        "https://www.hireschema.com/brand/email-logo.svg"
    )


def test_brand_shell_includes_logo_and_lime_cta() -> None:
    html = brand_shell(
        "Test heading",
        "<p>Body</p>",
        "https://www.hireschema.com/dashboard",
        "Go",
        app_base="https://www.hireschema.com",
        preheader="Hidden preview",
    )
    assert "email-logo.svg" in html
    assert "#B5FF6B" in html
    assert "Test heading" in html
    assert "Hidden preview" in html


def test_welcome_email_candidate_branded() -> None:
    subject, html = render_welcome_email(
        role="candidate",
        full_name="Priya",
        app_base_url="https://www.hireschema.com",
    )
    assert "Welcome" in subject
    assert "Aarya" in html
    assert "email-logo.svg" in html


def test_first_job_found_email_copy() -> None:
    subject, html = render_first_job_found_email(
        full_name="Rahul",
        job_title="Senior Engineer",
        company_name="Acme",
        score_pct=78,
        app_base_url="https://www.hireschema.com",
        job_id="job-123",
    )
    assert "first" in subject.lower()
    assert "Senior Engineer" in html
    assert "78" in html
    assert "email-logo.svg" in html


def test_intro_requested_candidate_email() -> None:
    subject, html = render_intro_requested_candidate_email(
        full_name="Sam",
        job_title="PM",
        company_name="Beta Co",
        app_base_url="https://www.hireschema.com",
    )
    assert "intro" in subject.lower()
    assert "PM" in html
    assert "Beta Co" in html


def test_recruiter_intro_request_email() -> None:
    subject, html = render_recruiter_intro_request_email(
        recruiter_name="Alex",
        candidate_name="Jordan",
        job_title="Designer",
        app_base_url="https://www.hireschema.com",
    )
    assert "intro" in subject.lower()
    assert "Jordan" in html
    assert "Designer" in html


def test_recruiter_approach_candidate_email() -> None:
    subject, html = render_recruiter_approach_candidate_email(
        candidate_name="Taylor",
        recruiter_name="Morgan",
        job_title="Analyst",
        company_name="Gamma",
        app_base_url="https://www.hireschema.com",
    )
    assert "recruiter" in subject.lower() or "connect" in subject.lower()
    assert "Morgan" in html
    assert "Analyst" in html


@pytest.mark.asyncio
async def test_send_first_job_found_dedupes() -> None:
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.fetchrow = AsyncMock(
        side_effect=[
            {
                "user_id": user_id,
                "email": "user@example.com",
                "full_name": "User",
            },
            {"?": 1},  # _already_sent
        ]
    )
    settings = Settings(
        resend_api_key="re_test_key_123456789012345678901234",
        resend_from_email="noreply@hireschema.com",
    )

    with patch(
        "hireloop_api.services.email.lifecycle_emails._send_html_email",
        new_callable=AsyncMock,
    ) as send_mock:
        result = await send_first_job_found_email(
            db,
            settings,
            candidate_id=str(candidate_id),
            job_id=str(uuid.uuid4()),
            job_title="Engineer",
            company_name="Co",
            overall_score=0.72,
        )

    assert result == {"sent": False, "skipped": "already_sent"}
    send_mock.assert_not_awaited()
