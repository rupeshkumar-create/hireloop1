"""Approve-first intro follow-ups + thank-you draft helpers."""

from __future__ import annotations

from hireloop_api.services.intro_followups import NUDGE_AFTER_HOURS, run_intro_followup_sweep
from hireloop_api.services.intro_outbound import (
    followup_draft_bodies,
    thankyou_draft_bodies,
)


def test_followup_draft_bodies_include_role_and_name() -> None:
    d = followup_draft_bodies("Priya Sharma", "Backend Engineer", "Rupesh")
    assert "Priya" in d["body_text"]
    assert "Backend Engineer" in d["body_text"]
    assert "Rupesh" in d["body_text"]
    assert "<p>" in d["body_html"]


def test_thankyou_draft_bodies_have_subject() -> None:
    d = thankyou_draft_bodies("Alex Kim", "GTM Lead", "Rupesh", "Acme")
    assert "Thank you" in d["subject"]
    assert "GTM Lead" in d["body_text"]
    assert "Acme" in d["body_text"]


def test_nudge_window_is_72_hours() -> None:
    assert NUDGE_AFTER_HOURS == 72


class _FakeSettings:
    google_client_id = "id"
    google_client_secret = "secret"
    allowed_origins: tuple[str, ...] = ("https://hireschema.com",)
    public_app_url = "https://hireschema.com"


class _FakeDb:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.rows = [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "candidate_id": "22222222-2222-2222-2222-222222222222",
                "gmail_thread_id": "thread-1",
                "gmail_subject": "Re: Backend Engineer",
                "job_title": "Backend Engineer",
                "company_name": "Acme",
                "hm_name": "Priya Sharma",
                "hm_email": "priya@acme.test",
                "user_id": "33333333-3333-3333-3333-333333333333",
                "candidate_name": "Rupesh",
            }
        ]

    async def fetch(self, query: str, *args: object) -> list[dict]:
        assert "followup_draft_at IS NULL" in query
        assert "nudged_at IS NULL" in query
        return list(self.rows)

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        if "followup_draft_email" in query:
            return "UPDATE 1"
        return "UPDATE 0"

    async def fetchval(self, query: str, *args: object) -> object:
        return False


import pytest


@pytest.mark.asyncio
async def test_followup_sweep_creates_draft_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb()

    async def fake_already(*_a: object, **_k: object) -> bool:
        return False

    async def fake_log(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(
        "hireloop_api.services.notifications._already_notified",
        fake_already,
    )
    monkeypatch.setattr(
        "hireloop_api.services.notifications._log_in_app",
        fake_log,
    )
    monkeypatch.setattr(
        "hireloop_api.services.notifications._app_base",
        lambda _s: "https://hireschema.com",
    )

    drafted = await run_intro_followup_sweep(db, _FakeSettings())  # type: ignore[arg-type]
    assert drafted == 1
    assert any("followup_draft_email" in q for q, _ in db.executed)
    assert not any("gmail" in q.lower() and "send" in q.lower() for q, _ in db.executed)
