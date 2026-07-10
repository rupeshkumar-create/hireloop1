"""API email provider routing — Resend only (SMTP reserved for Supabase Auth)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hireloop_api.config import Settings
from hireloop_api.services.email.transactional import _send_html_email
from hireloop_api.services.notifications import _send_html


@pytest.mark.asyncio
async def test_send_html_email_uses_resend_not_smtp() -> None:
    settings = Settings(
        resend_api_key="re_test_key_123456789012345678901234",
        resend_from_email="noreply@hireschema.com",
        smtp_host="smtp.gmail.com",
        smtp_user="user@gmail.com",
        smtp_password="app-password",
    )

    with (
        patch(
            "hireloop_api.services.email.transactional.ResendService.send",
            new_callable=AsyncMock,
            return_value=True,
        ) as resend_send,
        patch(
            "hireloop_api.services.email.transactional.ResendService.close",
            new_callable=AsyncMock,
        ),
        patch(
            "hireloop_api.services.email.smtp_service.SmtpService.send",
            new_callable=AsyncMock,
        ) as smtp_send,
    ):
        sent = await _send_html_email(
            settings,
            to_email="user@example.com",
            subject="Test",
            html="<p>hi</p>",
        )

    assert sent is True
    resend_send.assert_awaited_once()
    smtp_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_notifications_send_html_uses_resend_only() -> None:
    settings = Settings(
        resend_api_key="re_test_key_123456789012345678901234",
        resend_from_email="noreply@hireschema.com",
        smtp_host="smtp.gmail.com",
        smtp_user="user@gmail.com",
        smtp_password="app-password",
    )

    with (
        patch(
            "hireloop_api.services.notifications.ResendService.send",
            new_callable=AsyncMock,
            return_value=True,
        ) as resend_send,
        patch(
            "hireloop_api.services.notifications.ResendService.close",
            new_callable=AsyncMock,
        ),
        patch(
            "hireloop_api.services.email.smtp_service.SmtpService.send",
            new_callable=AsyncMock,
        ) as smtp_send,
    ):
        sent = await _send_html(
            settings, to_email="user@example.com", subject="Test", html="<p>hi</p>"
        )

    assert sent is True
    resend_send.assert_awaited_once()
    smtp_send.assert_not_awaited()
