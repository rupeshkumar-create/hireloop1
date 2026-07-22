"""Voice scheduling is candidate-owned reminder convenience, not capacity."""

from __future__ import annotations

import asyncio
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
    def __init__(self, db: BookingDb) -> None:
        self.db = db

    async def __aenter__(self) -> None:
        self.db.events.append("transaction_enter")

    async def __aexit__(self, *args: object) -> None:
        self.db.events.append("transaction_exit")


class BookingDb:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.user_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()
        self.duplicate = duplicate
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.events: list[str] = []

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    async def fetchval(self, query: str, *args: object) -> None:
        normalized = " ".join(query.split())
        if "pg_advisory_xact_lock" in normalized and "hashtextextended" in normalized:
            self.events.append("advisory_lock")
            return None
        raise AssertionError(f"Unrecognised fetchval query: {normalized}")

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        normalized = " ".join(query.split())
        if "FROM public.candidates" in normalized:
            return {"id": self.candidate_id}
        if "date_trunc('minute', scheduled_at)" in normalized:
            self.events.append("duplicate_check")
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
            self.events.append("session_insert")
            return "INSERT 0 1"
        if "UPDATE public.voice_sessions" in normalized and "calendar_event_id" in normalized:
            self.events.append("calendar_id_update")
            return "UPDATE 1"
        raise AssertionError(f"Unrecognised execute query: {normalized}")


class _Calendar:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def create_event(self, **kwargs: str) -> tuple[str, None]:
        self.calls.append(kwargs)
        return "event-1", None


class _UnavailableCalendar(_Calendar):
    async def create_event(self, **kwargs: str) -> tuple[None, None]:
        self.calls.append(kwargs)
        return None, None


class ConcurrentBookingDb(BookingDb):
    def __init__(self) -> None:
        super().__init__()
        self._lock = asyncio.Lock()
        self._lock_owner: asyncio.Task[object] | None = None
        self.booked = False

    async def fetchval(self, query: str, *args: object) -> None:
        normalized = " ".join(query.split())
        if "pg_advisory_xact_lock" not in normalized:
            raise AssertionError(f"Unrecognised fetchval query: {normalized}")
        await self._lock.acquire()
        self._lock_owner = asyncio.current_task()
        self.events.append("advisory_lock")

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        normalized = " ".join(query.split())
        if "FROM public.candidates" in normalized:
            return {"id": self.candidate_id}
        if "date_trunc('minute', scheduled_at)" in normalized:
            assert self._lock_owner is asyncio.current_task()
            self.events.append("duplicate_check")
            return {"id": uuid.uuid4()} if self.booked else None
        if "FROM public.gmail_tokens" in normalized:
            return None
        raise AssertionError(f"Unrecognised fetchrow query: {normalized}")

    async def execute(self, query: str, *args: object) -> str:
        normalized = " ".join(query.split())
        self.execute_calls.append((normalized, args))
        if "INSERT INTO public.voice_sessions" in normalized:
            assert self._lock_owner is asyncio.current_task()
            assert args[4] is None, "calendar enrichment must happen after booking commit"
            self.booked = True
            self.events.append("session_insert")
            return "INSERT 0 1"
        if "UPDATE public.voice_sessions" in normalized and "calendar_event_id" in normalized:
            assert self._lock_owner is None
            self.events.append("calendar_id_update")
            return "UPDATE 1"
        raise AssertionError(f"Unrecognised execute query: {normalized}")

    def transaction(self) -> _ConcurrentTransaction:
        return _ConcurrentTransaction(self)


class _ConcurrentTransaction(_Transaction):
    def __init__(self, db: ConcurrentBookingDb) -> None:
        super().__init__(db)
        self.db = db

    async def __aexit__(self, *args: object) -> None:
        self.db.events.append("transaction_exit")
        if self.db._lock_owner is asyncio.current_task():
            self.db._lock_owner = None
            self.db._lock.release()


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
async def test_concurrent_same_candidate_minute_creates_one_booking_and_calendar_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = ConcurrentBookingDb()
    calendar = _Calendar()
    monkeypatch.setattr(voice_sessions, "_get_calendar_service", lambda settings, db: calendar)
    body = voice_sessions.BookSessionRequest(start_time="2099-07-23T05:00:20Z")
    user = {"id": str(db.user_id), "email": "candidate@example.com"}
    settings = Settings(_env_file=None, environment="test")

    results = await asyncio.gather(
        voice_sessions.book_session(body, current_user=user, settings=settings, db=db),
        voice_sessions.book_session(body, current_user=user, settings=settings, db=db),
        return_exceptions=True,
    )

    assert sum(isinstance(result, voice_sessions.BookSessionResponse) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, voice_sessions.HTTPException)]
    assert len(conflicts) == 1
    assert conflicts[0].status_code == 409
    assert len(calendar.calls) == 1
    assert db.events.count("session_insert") == 1
    assert db.events.index("advisory_lock") < db.events.index("duplicate_check")
    assert db.events.index("duplicate_check") < db.events.index("session_insert")
    assert db.events.index("session_insert") < db.events.index("transaction_exit")
    assert db.events.index("transaction_exit") < db.events.index("calendar_id_update")


@pytest.mark.asyncio
async def test_calendar_failure_keeps_in_app_booking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = BookingDb()
    calendar = _UnavailableCalendar()
    monkeypatch.setattr(voice_sessions, "_get_calendar_service", lambda settings, db: calendar)

    response = await voice_sessions.book_session(
        voice_sessions.BookSessionRequest(start_time="2099-07-23T05:00:00Z"),
        current_user={"id": str(db.user_id), "email": "candidate@example.com"},
        settings=Settings(_env_file=None, environment="test"),
        db=db,
    )

    assert response.session_id
    assert response.calendar_event_id is None
    assert db.events.count("session_insert") == 1
    assert "calendar_id_update" not in db.events


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
