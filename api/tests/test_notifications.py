from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from hireloop_api.config import Settings
from hireloop_api.services import notifications


class _ReminderDb:
    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FROM public.voice_sessions" in query:
            return {
                "status": "scheduled",
                "email": "candidate@example.com",
                "full_name": "Priya",
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

    async def _send_category_email(*args: object, **kwargs: Any) -> dict[str, Any]:
        template_data.update(kwargs["template_data"])
        return {"sent": False}

    monkeypatch.setattr(notifications, "send_category_email", _send_category_email)

    result = await notifications.send_interview_reminder_email(
        _ReminderDb(),  # type: ignore[arg-type]
        Settings(
            _env_file=None,
            environment="test",
            public_app_url="https://www.hireschema.com",
        ),
        user_id=str(UUID("11111111-1111-4111-8111-111111111111")),
        session_id=str(session_id),
        session_type="career_chat",
        scheduled_at=datetime(2099, 7, 23, 5, tzinfo=UTC),
    )

    assert result == {"sent": False}
    assert template_data["session_label"] == "Start your private 15-minute call"
    assert template_data["cta_url"].endswith(
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


def test_career_chat_email_details_reject_invalid_session_id() -> None:
    settings = Settings(_env_file=None, environment="test")

    with pytest.raises(ValueError):
        notifications._voice_session_email_details(
            settings,
            session_id="not-a-uuid&redirect=https://evil.example",
            session_type="career_chat",
        )
