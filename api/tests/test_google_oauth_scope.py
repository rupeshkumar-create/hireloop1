"""
Google OAuth connect must request BOTH gmail.send (P13) and calendar.events (P07)
so a candidate connects Google once and unlocks outreach + voice-session booking.
"""

from __future__ import annotations

from hireloop_api.routes.gmail import _CALENDAR_SCOPE, _GMAIL_SCOPE, _GOOGLE_SCOPE


def test_connect_scope_includes_send_and_calendar() -> None:
    assert _GMAIL_SCOPE in _GOOGLE_SCOPE
    assert _CALENDAR_SCOPE in _GOOGLE_SCOPE


def test_scopes_are_least_privilege() -> None:
    # Never request full mail/calendar read scopes.
    assert "auth/gmail.send" in _GMAIL_SCOPE
    assert "auth/calendar.events" in _CALENDAR_SCOPE
    assert "gmail.readonly" not in _GOOGLE_SCOPE
    assert "auth/calendar " not in f"{_GOOGLE_SCOPE} "  # not the full calendar scope
