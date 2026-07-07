"""Tests for welcome email delivery and deduplication."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hireloop_api.config import Settings
from hireloop_api.services.email.transactional import maybe_send_signup_confirmation
from hireloop_api.services.notifications import (
    default_notification_prefs,
    ensure_default_notification_prefs,
)


def test_default_notification_prefs_match_settings_categories() -> None:
    prefs = default_notification_prefs(marketing_emails=False)
    assert prefs["job_match_alerts"]["email"] is True
    assert prefs["platform_updates"]["email"] is False
    assert "intro_status" in prefs


@pytest.mark.asyncio
async def test_welcome_email_sent_when_profile_already_exists() -> None:
    """Seeded demo users have candidate rows but may never have received welcome."""
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.fetchrow = AsyncMock(
        side_effect=[
            None,  # _signup_email_already_sent
            {
                "email": "priya.candidate@hireschema.com",
                "full_name": "Priya",
                "role": "candidate",
            },
        ]
    )
    db.execute = AsyncMock()
    settings = Settings(
        resend_api_key="re_test_key_123456789012345678901234",
        resend_from_email="noreply@hireschema.com",
        public_app_url="https://app.hireschema.com",
    )

    with patch(
        "hireloop_api.services.email.transactional._send_html_email",
        new_callable=AsyncMock,
        return_value=True,
    ) as send_mock:
        result = await maybe_send_signup_confirmation(
            db,
            settings,
            user_id=user_id,
        )

    assert result == {"sent": True}
    send_mock.assert_awaited_once()
    db.execute.assert_awaited()


@pytest.mark.asyncio
async def test_welcome_email_skipped_when_already_sent() -> None:
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"?": 1})  # already sent
    settings = Settings(resend_api_key="re_test_key_123456789012345678901234")

    with patch(
        "hireloop_api.services.email.transactional._send_html_email",
        new_callable=AsyncMock,
    ) as send_mock:
        result = await maybe_send_signup_confirmation(
            db,
            settings,
            user_id=user_id,
            email="user@example.com",
            full_name="User",
            role="candidate",
        )

    assert result == {"sent": False, "skipped": "already_sent"}
    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_default_notification_prefs_seeds_empty() -> None:
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"notification_prefs": None})
    db.execute = AsyncMock()

    await ensure_default_notification_prefs(db, user_id)

    db.execute.assert_awaited_once()
    args = db.execute.await_args.args
    assert args[0].strip().startswith("UPDATE public.users")
    assert "job_match_alerts" in args[2]


@pytest.mark.asyncio
async def test_ensure_default_notification_prefs_skips_existing() -> None:
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.fetchrow = AsyncMock(
        return_value={"notification_prefs": {"job_match_alerts": {"email": False}}}
    )
    db.execute = AsyncMock()

    await ensure_default_notification_prefs(db, user_id)

    db.execute.assert_not_awaited()
