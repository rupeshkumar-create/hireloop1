from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from hireloop_api.config import Settings
from hireloop_api.services import notifications
from hireloop_api.services.email.notification_templates import render_notification_email


class _ReminderDb:
    scheduled_at = datetime(2099, 8, 24, 6, tzinfo=UTC)

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FROM public.voice_sessions" in query:
            return {
                "status": "scheduled",
                "email": "candidate@example.com",
                "full_name": "Priya",
                "session_type": "career_chat",
                "scheduled_at": self.scheduled_at,
            }
        if "FROM public.notifications" in query:
            return None
        raise AssertionError(f"Unexpected query: {query}")


@pytest.mark.asyncio
async def test_career_chat_reminder_uses_private_call_label_and_deep_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid4()
    template_data: dict[str, Any] = {}
    rendered: dict[str, str] = {}
    in_app: dict[str, Any] = {}

    async def _send_category_email(*args: object, **kwargs: Any) -> dict[str, Any]:
        template_data.update(kwargs["template_data"])
        subject, html = render_notification_email(kwargs["category"], kwargs["template_data"])
        rendered.update(subject=subject, html=html)
        return {"sent": True}

    async def _log_in_app(*args: object, **kwargs: Any) -> None:
        in_app.update(kwargs)

    monkeypatch.setattr(notifications, "send_category_email", _send_category_email)
    monkeypatch.setattr(notifications, "_log_in_app", _log_in_app)

    result = await notifications.send_interview_reminder_email(
        _ReminderDb(),  # type: ignore[arg-type]
        Settings(
            _env_file=None,
            environment="test",
            public_app_url="https://www.hireschema.com",
        ),
        user_id=str(UUID("11111111-1111-4111-8111-111111111111")),
        session_id=str(session_id),
        session_type="mock_interview",
        scheduled_at=datetime(2099, 7, 23, 5, tzinfo=UTC),
    )

    assert result == {"sent": True}
    assert template_data["session_label"] == "Private 15-minute career call"
    assert template_data["cta_url"].endswith(
        f"/dashboard?voice=deep&scheduled_session_id={session_id}"
    )
    assert rendered["subject"] == "Reminder: Private 15-minute career call tomorrow"
    assert "Your <strong>Private 15-minute career call</strong> with Aarya" in rendered["html"]
    assert "Mon 24 Aug 2099, 06:00 UTC" in rendered["html"]
    assert "voice=deep&amp;scheduled_session_id=" in rendered["html"]
    assert "Start your private 15-minute call" in rendered["html"]
    assert in_app["title"] == "Reminder: Private 15-minute career call tomorrow"
    assert in_app["data"]["deep_link"] == (
        f"/dashboard?voice=deep&scheduled_session_id={session_id}"
    )


class _BookingDb:
    async def fetchrow(self, query: str, *args: object) -> dict[str, Any]:
        assert "FROM public.users" in query
        return {"email": "candidate@example.com", "full_name": "Priya"}


@pytest.mark.asyncio
async def test_career_chat_booking_confirmation_renders_as_a_noun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = uuid4()
    rendered: dict[str, str] = {}
    in_app: dict[str, Any] = {}

    async def _send_category_email(*args: object, **kwargs: Any) -> dict[str, Any]:
        subject, html = render_notification_email(kwargs["category"], kwargs["template_data"])
        rendered.update(subject=subject, html=html)
        return {"sent": True}

    async def _log_in_app(*args: object, **kwargs: Any) -> None:
        in_app.update(kwargs)

    monkeypatch.setattr(notifications, "send_category_email", _send_category_email)
    monkeypatch.setattr(notifications, "_log_in_app", _log_in_app)

    await notifications.notify_interview_booked(
        _BookingDb(),  # type: ignore[arg-type]
        Settings(
            _env_file=None,
            environment="test",
            public_app_url="https://www.hireschema.com",
        ),
        user_id=str(UUID("11111111-1111-4111-8111-111111111111")),
        session_id=str(session_id),
        session_type="career_chat",
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
    )

    assert rendered["subject"] == "Booked: Private 15-minute career call with Aarya"
    assert "Your <strong>Private 15-minute career call</strong> with Aarya" in rendered["html"]
    assert "Start your private 15-minute call" in rendered["html"]
    assert in_app["title"] == "Private 15-minute career call booked"
    assert in_app["data"]["deep_link"] == (
        f"/dashboard?voice=deep&scheduled_session_id={session_id}"
    )


def test_mock_interview_email_details_keep_existing_label_and_dashboard_cta() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        public_app_url="https://www.hireschema.com",
    )

    label, cta_url = notifications._voice_session_email_details(
        settings,
        session_id=str(uuid4()),
        session_type="mock_interview",
    )

    assert label == "Mock Interview"
    assert cta_url == "https://www.hireschema.com/dashboard"
    subject, html = render_notification_email(
        "interview_reminders",
        {
            "full_name": "Priya",
            "session_label": label,
            "scheduled_label": "Mon 24 Aug 2099, 06:00 UTC",
            "is_reminder": False,
            "cta_url": cta_url,
        },
    )
    assert subject == "Booked: Mock Interview with Aarya"
    assert "Your <strong>Mock Interview</strong> with Aarya" in html
    assert "Open Hireschema" in html
    assert "Start your private 15-minute call" not in html


def test_career_chat_email_details_reject_invalid_session_id() -> None:
    settings = Settings(_env_file=None, environment="test")

    with pytest.raises(ValueError):
        notifications._voice_session_email_details(
            settings,
            session_id="not-a-uuid&redirect=https://evil.example",
            session_type="career_chat",
        )


@pytest.mark.asyncio
async def test_reminder_skips_deleted_or_missing_owner_without_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[str] = []

    class _MissingOwnerDb:
        async def fetchrow(self, query: str, *args: object) -> None:
            queries.append(query)
            return None

    async def _unexpected(*args: object, **kwargs: Any) -> None:
        raise AssertionError("Deleted or missing owners must not receive reminders")

    monkeypatch.setattr(notifications, "send_category_email", _unexpected)
    monkeypatch.setattr(notifications, "_log_in_app", _unexpected)

    result = await notifications.send_interview_reminder_email(
        _MissingOwnerDb(),  # type: ignore[arg-type]
        Settings(_env_file=None, environment="test"),
        user_id=str(UUID("11111111-1111-4111-8111-111111111111")),
        session_id=str(uuid4()),
        session_type="career_chat",
        scheduled_at=datetime(2099, 7, 23, 5, tzinfo=UTC),
    )

    assert result == {"sent": False, "skipped": "not_scheduled"}
    assert "c.deleted_at IS NULL" in queries[0]
    assert "u.deleted_at IS NULL" in queries[0]
