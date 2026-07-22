"""
In-house voice-session booking — Google Calendar (P07).

Replaces the former Cal.com integration. Booking is owned by Hireschema:

  1. GET  /slots  → convenient future reminder times during business hours (IST).
  2. POST /book   → always creates a `voice_sessions` row. If the candidate has a
                    Google token with the `calendar.events` scope (same OAuth app
                    as P13 Gmail), we also create a Calendar reminder event
                    and store its id in voice_sessions.calendar_event_id.
  3. Cancel       → deletes the Calendar event if present, marks the row cancelled.

Graceful degradation (R-style): if the calendar scope isn't connected, the in-app
slot row IS the booking — booking never hard-fails on a missing key.

Calendar API: https://developers.google.com/calendar/api/v3/reference/events
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg
import httpx
import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"

IST = ZoneInfo("Asia/Kolkata")

# Business hours for AI career calls, in IST.
BUSINESS_START_HOUR = 10  # first slot starts 10:00 IST
BUSINESS_END_HOUR = 18  # last slot must END by 18:00 IST
SLOT_MINUTES = 15
MAX_SLOTS = 40  # cap the list we hand the UI/agent


class AvailableSlot(BaseModel):
    start_time: str  # ISO 8601 UTC
    end_time: str  # ISO 8601 UTC
    timezone: str = "Asia/Kolkata"


def generate_slots(
    days_ahead: int = 7,
    booked_starts: set[str] | None = None,
    *,
    now: datetime | None = None,
) -> list[AvailableSlot]:
    """
    Build convenient 15-minute reminder slots across the next `days_ahead` days.

    Pure function (no I/O) so it's trivially testable:
      - Mon-Sat, BUSINESS_START_HOUR..BUSINESS_END_HOUR IST, SLOT_MINUTES grid.
      - Skips slots already started (<= now) and any in `booked_starts`
        (a set of ISO-8601 UTC start strings).
    Returns up to MAX_SLOTS slots with UTC start/end ISO strings.
    """
    booked = booked_starts or set()
    now = (now or datetime.now(UTC)).astimezone(UTC)
    today_ist = now.astimezone(IST).date()

    slots: list[AvailableSlot] = []
    for day_offset in range(days_ahead + 1):
        day = today_ist + timedelta(days=day_offset)
        if day.weekday() == 6:  # Sunday off (Mon=0 .. Sun=6)
            continue

        hour, minute = BUSINESS_START_HOUR, 0
        while True:
            start_ist = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
            end_ist = start_ist + timedelta(minutes=SLOT_MINUTES)
            # Last slot must end by close of business.
            if end_ist.hour > BUSINESS_END_HOUR or (
                end_ist.hour == BUSINESS_END_HOUR and end_ist.minute > 0
            ):
                break

            start_utc = start_ist.astimezone(UTC)
            end_utc = end_ist.astimezone(UTC)
            start_iso = start_utc.isoformat()

            if start_utc > now and start_iso not in booked:
                slots.append(AvailableSlot(start_time=start_iso, end_time=end_utc.isoformat()))
                if len(slots) >= MAX_SLOTS:
                    return slots

            minute += SLOT_MINUTES
            hour += minute // 60
            minute %= 60

    return slots


class GoogleCalendarService:
    """
    Creates/cancels Google Calendar events for booked voice sessions, reusing the
    candidate's Google OAuth token (stored in `gmail_tokens` by the P13 flow).

    All methods degrade gracefully: if there's no token or no calendar scope,
    create_event returns (None, None) and the caller falls back to the in-app slot.
    """

    def __init__(
        self,
        google_client_id: str,
        google_client_secret: str,
        db: asyncpg.Connection,
        calendar_id: str = "primary",
    ) -> None:
        self._client_id = google_client_id
        self._client_secret = google_client_secret
        self._db = db
        self._calendar_id = calendar_id

    # ── Token management (mirrors GmailOAuthService; shared gmail_tokens row) ──

    async def _get_token(self, candidate_id: str) -> str | None:
        row = await self._db.fetchrow(
            "SELECT access_token, refresh_token, token_expiry, scopes "
            "FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
            candidate_id,
        )
        if not row:
            return None

        scopes = row.get("scopes") or []
        if _CALENDAR_SCOPE not in scopes and "calendar" not in " ".join(scopes):
            logger.info("calendar_scope_missing", candidate_id=candidate_id)
            return None

        expires_at = row["token_expiry"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (expires_at - datetime.now(UTC)).total_seconds() < 60:
            return await self._refresh_token(candidate_id, row["refresh_token"])
        return row["access_token"]

    async def _refresh_token(self, candidate_id: str, refresh_token: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    _OAUTH_TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
            res.raise_for_status()
            data = res.json()
            new_token = data["access_token"]
            expiry = datetime.now(UTC) + timedelta(seconds=data.get("expires_in", 3600))
            await self._db.execute(
                "UPDATE public.gmail_tokens SET access_token=$1, token_expiry=$2, "
                "updated_at=NOW() WHERE candidate_id=$3::uuid",
                new_token,
                expiry,
                candidate_id,
            )
            return new_token
        except Exception as exc:
            logger.error("calendar_token_refresh_failed", candidate_id=candidate_id, error=str(exc))
            return None

    # ── Event lifecycle ───────────────────────────────────────────────────────

    async def create_event(
        self,
        candidate_id: str,
        start_iso: str,
        end_iso: str,
        summary: str,
        description: str,
        attendee_email: str,
    ) -> tuple[str | None, str | None]:
        """
        Create a Calendar reminder event for an in-app call.
        Returns (event_id, None), or (None, None) when no calendar token is
        available (caller keeps the in-app slot as the booking).
        """
        token = await self._get_token(candidate_id)
        if not token:
            return None, None

        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_iso, "timeZone": "Asia/Kolkata"},
            "attendees": [{"email": attendee_email}],
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    f"{_CALENDAR_API}/calendars/{self._calendar_id}/events",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"sendUpdates": "all"},
                    json=body,
                )
            if res.status_code not in (200, 201):
                logger.error(
                    "calendar_create_failed",
                    candidate_id=candidate_id,
                    status=res.status_code,
                    body=res.text[:200],
                )
                return None, None
            data = res.json()
            logger.info(
                "calendar_event_created", candidate_id=candidate_id, event_id=data.get("id")
            )
            return data.get("id"), None
        except Exception as exc:
            logger.error("calendar_create_error", candidate_id=candidate_id, error=str(exc))
            return None, None

    async def delete_event(self, candidate_id: str, event_id: str) -> bool:
        token = await self._get_token(candidate_id)
        if not token:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.delete(
                    f"{_CALENDAR_API}/calendars/{self._calendar_id}/events/{event_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"sendUpdates": "all"},
                )
            return res.status_code in (200, 204, 410)  # 410 = already gone
        except Exception as exc:
            logger.error("calendar_delete_error", candidate_id=candidate_id, error=str(exc))
            return False
