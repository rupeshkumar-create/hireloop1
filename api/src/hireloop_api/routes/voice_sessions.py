"""
Voice session routes — booking 20-min AI career calls (in-house, Google Calendar).

GET    /api/v1/voice-sessions/slots          → available slots (business hours, minus booked)
POST   /api/v1/voice-sessions/book           → create booking + voice_session row
GET    /api/v1/voice-sessions                → candidate's session history
DELETE /api/v1/voice-sessions/{id}/cancel    → cancel a booking

Booking is owned by Hireschema. If the candidate has connected Google with the
calendar.events scope (same OAuth app as P13), we also create a Calendar event
with a Meet link; otherwise the in-app slot row is the booking.
"""

import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.services.google_calendar import (
    SLOT_MINUTES,
    AvailableSlot,
    GoogleCalendarService,
    generate_slots,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/voice-sessions", tags=["voice-sessions"])


def _get_calendar_service(settings: Settings, db: asyncpg.Connection) -> GoogleCalendarService:
    return GoogleCalendarService(
        google_client_id=settings.google_client_id,
        google_client_secret=settings.google_client_secret,
        db=db,
        calendar_id=getattr(settings, "google_calendar_id", "primary") or "primary",
    )


class BookSessionRequest(BaseModel):
    start_time: str  # ISO 8601 UTC
    session_type: str = "career_chat"  # 'career_chat' | 'mock_interview'


class BookSessionResponse(BaseModel):
    session_id: str
    calendar_event_id: str | None
    start_time: str
    end_time: str
    meet_url: str | None
    message: str
    calendar_connected: bool = False
    google_connect_hint: str | None = None


@router.get("/slots", response_model=list[AvailableSlot])
async def get_available_slots(
    days_ahead: int = 7,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[AvailableSlot]:
    """Return available 20-min AI career call slots for the next N days."""
    rows = await db.fetch(
        """
        SELECT scheduled_at FROM public.voice_sessions
        WHERE status = 'scheduled' AND scheduled_at >= NOW()
        """,
    )
    booked = {r["scheduled_at"].astimezone(UTC).isoformat() for r in rows if r["scheduled_at"]}
    return generate_slots(days_ahead=min(days_ahead, 14), booked_starts=booked)


@router.post("/book", response_model=BookSessionResponse, status_code=201)
async def book_session(
    body: BookSessionRequest,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> BookSessionResponse:
    """Book a 20-min AI career call slot."""
    if body.session_type not in ("career_chat", "mock_interview"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_type must be 'career_chat' or 'mock_interview'",
        )

    try:
        start_dt = datetime.fromisoformat(body.start_time.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="start_time must be ISO 8601") from exc
    if start_dt <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="start_time must be in the future")
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    # Guard against double-booking the same slot.
    clash = await db.fetchrow(
        "SELECT 1 FROM public.voice_sessions WHERE status = 'scheduled' AND scheduled_at = $1",
        start_dt,
    )
    if clash:
        raise HTTPException(status_code=409, detail="That slot was just taken — pick another.")

    # Create the Calendar event (enrichment; degrades to in-app slot if no scope).
    calendar = _get_calendar_service(settings, db)
    label = body.session_type.replace("_", " ").title()
    event_id, meet_url = await calendar.create_event(
        candidate_id=str(candidate["id"]),
        start_iso=start_dt.isoformat(),
        end_iso=end_dt.isoformat(),
        summary=f"Hireschema · {label} with Aarya",
        description="Your 20-minute AI career call. Join at the scheduled time.",
        attendee_email=current_user["email"],
    )

    session_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO public.voice_sessions
          (id, candidate_id, session_type, status, scheduled_at, calendar_event_id)
        VALUES ($1, $2, $3, 'scheduled', $4, $5)
        """,
        uuid.UUID(session_id),
        candidate["id"],
        body.session_type,
        start_dt,
        event_id,
    )

    logger.info(
        "voice_session_booked",
        session_id=session_id,
        session_type=body.session_type,
        calendar_event_id=event_id,
        has_meet=bool(meet_url),
    )

    try:
        from hireloop_api.services.notifications import notify_interview_booked

        await notify_interview_booked(
            db,
            settings,
            user_id=str(current_user["id"]),
            session_id=session_id,
            session_type=body.session_type,
            scheduled_at=start_dt,
        )
    except Exception as exc:
        logger.warning("interview_booked_notify_failed", error=str(exc)[:200])

    msg = f"Your {body.session_type.replace('_', ' ')} is booked"
    calendar_connected = False
    google_hint: str | None = None
    if event_id and meet_url:
        msg += f" — Meet link added to your Google Calendar: {meet_url}"
        calendar_connected = True
    elif event_id:
        msg += " — calendar invite created on your Google Calendar."
        calendar_connected = True
    else:
        msg += "."
        # Check whether they have a token at all (scope may be missing).
        token_row = await db.fetchrow(
            "SELECT scopes FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
            candidate["id"],
        )
        if token_row is None:
            google_hint = (
                "Connect Google (Gmail + Calendar) in Settings so the next booking "
                "gets a Meet link on your calendar."
            )
            msg += " " + google_hint
        else:
            google_hint = "Reconnect Google and grant calendar access to get a Meet link next time."
            msg += " " + google_hint
        calendar_connected = False

    return BookSessionResponse(
        session_id=session_id,
        calendar_event_id=event_id,
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        meet_url=meet_url,
        message=msg,
        calendar_connected=calendar_connected,
        google_connect_hint=google_hint,
    )


@router.get("", response_model=list[dict])
async def list_sessions(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """Return all voice sessions for the current candidate."""
    rows = await db.fetch(
        """
        SELECT vs.id, vs.session_type, vs.status, vs.scheduled_at,
               vs.started_at, vs.ended_at, vs.duration_secs, vs.calendar_event_id
        FROM public.voice_sessions vs
        JOIN public.candidates c ON c.id = vs.candidate_id
        WHERE c.user_id = $1
        ORDER BY vs.scheduled_at DESC
        LIMIT 50
        """,
        uuid.UUID(current_user["id"]),
    )
    return [dict(r) for r in rows]


@router.delete("/{session_id}/cancel", status_code=200)
async def cancel_session(
    session_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Cancel a scheduled voice session."""
    row = await db.fetchrow(
        """
        SELECT vs.id, vs.candidate_id, vs.calendar_event_id, vs.status
        FROM public.voice_sessions vs
        JOIN public.candidates c ON c.id = vs.candidate_id
        WHERE vs.id = $1 AND c.user_id = $2
        """,
        uuid.UUID(session_id),
        uuid.UUID(current_user["id"]),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if row["status"] != "scheduled":
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel session with status '{row['status']}'"
        )

    if row["calendar_event_id"]:
        calendar = _get_calendar_service(settings, db)
        await calendar.delete_event(str(row["candidate_id"]), row["calendar_event_id"])

    await db.execute(
        "UPDATE public.voice_sessions SET status='cancelled', updated_at=NOW() WHERE id=$1",
        row["id"],
    )

    return {"message": "Session cancelled successfully"}
