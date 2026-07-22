"""Voice scheduling is candidate-owned reminder convenience, not capacity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from hireloop_api.config import Settings
from hireloop_api.routes import voice_sessions
from hireloop_api.services.google_calendar import (
    BUSINESS_END_HOUR,
    BUSINESS_START_HOUR,
    MAX_SLOTS,
    GoogleCalendarService,
    generate_slots,
)

IST = ZoneInfo("Asia/Kolkata")


def _now_ist(y: int, m: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=IST).astimezone(UTC)


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class BookingDb:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.user_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()
        self.duplicate = duplicate
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        normalized = " ".join(query.split())
        if "FROM public.candidates" in normalized:
            return {"id": self.candidate_id}
        if "date_trunc('minute', scheduled_at)" in normalized:
            return {"id": uuid.uuid4()} if self.duplicate else None
        if "FROM public.gmail_tokens" in normalized:
            return None
        raise AssertionError(f"Unrecognised fetchrow query: {normalized}")

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        raise AssertionError(f"Slots must not query bookings: {' '.join(query.split())}")

    async def execute(self, query: str, *args: object) -> str:
        normalized = " ".join(query.split())
        self.execute_calls.append((normalized, args))
        if "INSERT INTO public.voice_sessions" in normalized:
            return "INSERT 0 1"
        raise AssertionError(f"Unrecognised execute query: {normalized}")


class _Calendar:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def create_event(self, **kwargs: str) -> tuple[str, None]:
        self.calls.append(kwargs)
        return "event-1", None


def test_slots_are_15min_within_business_hours() -> None:
    now = _now_ist(2026, 6, 15, 7, 0)
    slots = generate_slots(days_ahead=0, now=now)
    assert slots
    assert all(
        datetime.fromisoformat(slot.end_time) - datetime.fromisoformat(slot.start_time)
        == timedelta(minutes=15)
        for slot in slots
    )
    first_ist = datetime.fromisoformat(slots[0].start_time).astimezone(IST)
    assert (first_ist.hour, first_ist.minute) == (BUSINESS_START_HOUR, 0)
    assert all(
        BUSINESS_START_HOUR
        <= datetime.fromisoformat(slot.start_time).astimezone(IST).hour
        < BUSINESS_END_HOUR
        for slot in slots
    )


@pytest.mark.asyncio
async def test_slots_endpoint_never_queries_other_candidates_bookings() -> None:
    db = BookingDb()
    slots = await voice_sessions.get_available_slots(days_ahead=1, current_user={}, db=db)
    assert slots


@pytest.mark.asyncio
async def test_booking_allows_same_time_for_another_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = BookingDb()
    calendar = _Calendar()
    monkeypatch.setattr(voice_sessions, "_get_calendar_service", lambda settings, db: calendar)

    response = await voice_sessions.book_session(
        voice_sessions.BookSessionRequest(start_time="2099-07-23T05:00:00Z"),
        current_user={"id": str(db.user_id), "email": "candidate@example.com"},
        settings=Settings(_env_file=None, environment="test"),
        db=db,
    )

    assert response.start_time == "2099-07-23T05:00:00+00:00"
    assert response.meet_url is None
    assert not any(
        "status = 'scheduled' AND scheduled_at = $1" in sql for sql, _ in db.fetchrow_calls
    )


@pytest.mark.asyncio
async def test_duplicate_candidate_career_chat_in_same_minute_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = BookingDb(duplicate=True)
    calendar = _Calendar()
    monkeypatch.setattr(voice_sessions, "_get_calendar_service", lambda settings, db: calendar)

    with pytest.raises(voice_sessions.HTTPException) as exc:
        await voice_sessions.book_session(
            voice_sessions.BookSessionRequest(start_time="2099-07-23T05:00:20Z"),
            current_user={"id": str(db.user_id), "email": "candidate@example.com"},
            settings=Settings(_env_file=None, environment="test"),
            db=db,
        )

    assert exc.value.status_code == 409
    assert calendar.calls == []


@pytest.mark.asyncio
async def test_booking_calendar_copy_uses_in_app_deep_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = BookingDb()
    calendar = _Calendar()
    monkeypatch.setattr(voice_sessions, "_get_calendar_service", lambda settings, db: calendar)

    response = await voice_sessions.book_session(
        voice_sessions.BookSessionRequest(start_time="2099-07-23T05:00:00Z"),
        current_user={"id": str(db.user_id), "email": "candidate@example.com"},
        settings=Settings(
            _env_file=None,
            environment="test",
            public_app_url="https://www.hireschema.com",
        ),
        db=db,
    )

    session_id = response.session_id
    assert "15-minute in-app call" in calendar.calls[0]["description"]
    assert (
        f"https://www.hireschema.com/dashboard?voice=deep&scheduled_session_id={session_id}"
        in calendar.calls[0]["description"]
    )
    assert response.meet_url is None
    assert "Meet" not in response.message
    assert "Meet" not in (response.google_connect_hint or "")


@pytest.mark.asyncio
async def test_calendar_request_has_no_conference_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    class _Response:
        status_code = 201
        text = ""

        @staticmethod
        def json() -> dict[str, str]:
            return {"id": "event-1", "hangoutLink": "https://meet.invalid/old"}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> _Response:
            requests.append({"url": url, **kwargs})
            return _Response()

    service = GoogleCalendarService("client", "secret", BookingDb())
    monkeypatch.setattr(service, "_get_token", _return_token)
    monkeypatch.setattr("hireloop_api.services.google_calendar.httpx.AsyncClient", _Client)

    event_id, meet_url = await service.create_event(
        candidate_id=str(uuid.uuid4()),
        start_iso="2099-07-23T05:00:00+00:00",
        end_iso="2099-07-23T05:15:00+00:00",
        summary="Career call",
        description="In-app reminder",
        attendee_email="candidate@example.com",
    )

    assert event_id == "event-1"
    assert meet_url is None
    assert "conferenceData" not in requests[0]["json"]
    assert "conferenceDataVersion" not in requests[0]["params"]


async def _return_token(candidate_id: str) -> str:
    return "token"


def test_past_slots_excluded() -> None:
    now = _now_ist(2026, 6, 15, 12, 5)
    assert all(
        datetime.fromisoformat(slot.start_time) > now
        for slot in generate_slots(days_ahead=0, now=now)
    )


def test_sunday_skipped() -> None:
    assert generate_slots(days_ahead=0, now=_now_ist(2026, 6, 14, 0, 1)) == []


def test_slot_count_capped() -> None:
    assert len(generate_slots(days_ahead=14, now=_now_ist(2026, 6, 15, 0, 1))) <= MAX_SLOTS
