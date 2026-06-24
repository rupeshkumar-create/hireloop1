"""P07 in-house booking — slot generation logic (Google Calendar swap, no Cal.com)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from hireloop_api.services.google_calendar import (
    BUSINESS_END_HOUR,
    BUSINESS_START_HOUR,
    MAX_SLOTS,
    SLOT_MINUTES,
    generate_slots,
)

IST = ZoneInfo("Asia/Kolkata")


def _now_ist(y: int, m: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=IST).astimezone(UTC)


def test_slots_are_20min_within_business_hours() -> None:
    # A Monday morning before business hours.
    now = _now_ist(2026, 6, 15, 7, 0)  # Mon 07:00 IST
    slots = generate_slots(days_ahead=0, now=now)
    assert slots, "should produce same-day slots"
    for s in slots:
        start = datetime.fromisoformat(s.start_time)
        end = datetime.fromisoformat(s.end_time)
        assert (end - start) == timedelta(minutes=SLOT_MINUTES)
        ist = start.astimezone(IST)
        assert BUSINESS_START_HOUR <= ist.hour < BUSINESS_END_HOUR
    # First slot of the day is 10:00 IST.
    first_ist = datetime.fromisoformat(slots[0].start_time).astimezone(IST)
    assert (first_ist.hour, first_ist.minute) == (BUSINESS_START_HOUR, 0)


def test_past_slots_excluded() -> None:
    now = _now_ist(2026, 6, 15, 12, 5)  # Mon 12:05 IST — mid-day
    slots = generate_slots(days_ahead=0, now=now)
    for s in slots:
        assert datetime.fromisoformat(s.start_time) > now


def test_booked_slots_excluded() -> None:
    now = _now_ist(2026, 6, 15, 7, 0)
    full = generate_slots(days_ahead=0, now=now)
    booked = {full[0].start_time}
    pruned = generate_slots(days_ahead=0, now=now, booked_starts=booked)
    assert full[0].start_time not in {s.start_time for s in pruned}
    assert len(pruned) == len(full) - 1


def test_sunday_skipped() -> None:
    # 2026-06-14 is a Sunday; ask for just that day.
    now = _now_ist(2026, 6, 14, 0, 1)
    slots = generate_slots(days_ahead=0, now=now)
    assert slots == []


def test_slot_count_capped() -> None:
    now = _now_ist(2026, 6, 15, 0, 1)
    slots = generate_slots(days_ahead=14, now=now)
    assert len(slots) <= MAX_SLOTS
