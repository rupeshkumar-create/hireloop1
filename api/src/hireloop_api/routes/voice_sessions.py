"""
Voice session routes — private 15-minute Aarya calls and reminder scheduling.

GET    /api/v1/voice-sessions/slots          → convenient future reminder times
POST   /api/v1/voice-sessions/book           → create booking + voice_session row
POST   /api/v1/voice-sessions/start          → start an instant or scheduled call
POST   /api/v1/voice-sessions/{id}/complete  → complete an owned active call
GET    /api/v1/voice-sessions                → candidate's session history
DELETE /api/v1/voice-sessions/{id}/cancel    → cancel a booking

Bookings are candidate-owned reminders, not scarce AI capacity. Google Calendar
is optional reminder enrichment; every call itself happens in the app.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.models.career_interview import CareerInterviewCoverage, InterviewTopic
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


class StartCareerCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: uuid.UUID
    scheduled_session_id: uuid.UUID | None = None
    consent: bool = Field(strict=True)
    consent_version: str = Field(
        default="career-call-v1",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
    )


class CareerCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    status: Literal["active", "completed"]
    scheduled_at: str | None = None
    started_at: str | None = None


class CompleteCareerCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completion_reason: Literal["candidate_ended", "time_limit", "coverage_complete", "interrupted"]
    duration_seconds: int = Field(ge=0, le=16 * 60, strict=True)


def _isoformat(value: object) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _career_call_response(row: asyncpg.Record | dict[str, object]) -> CareerCallResponse:
    return CareerCallResponse(
        id=str(row["id"]),
        conversation_id=str(row["conversation_id"]),
        status=str(row["status"]),
        scheduled_at=_isoformat(row.get("scheduled_at")),
        started_at=_isoformat(row.get("started_at")),
    )


@router.get("/slots", response_model=list[AvailableSlot])
async def get_available_slots(
    days_ahead: int = 7,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[AvailableSlot]:
    """Return convenient 15-minute reminder times; bookings are not inventory."""
    return generate_slots(days_ahead=min(days_ahead, 14))


@router.post("/book", response_model=BookSessionResponse, status_code=201)
async def book_session(
    body: BookSessionRequest,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> BookSessionResponse:
    """Book a candidate-owned reminder for a 15-minute in-app call."""
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

    if body.session_type == "career_chat":
        duplicate = await db.fetchrow(
            """
            SELECT id
            FROM public.voice_sessions
            WHERE candidate_id = $1::uuid
              AND session_type = 'career_chat'
              AND status = 'scheduled'
              AND date_trunc('minute', scheduled_at) = date_trunc('minute', $2::timestamptz)
            LIMIT 1
            """,
            candidate["id"],
            start_dt,
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="You already scheduled a career call for that minute.",
            )

    # Create the Calendar event (enrichment; degrades to in-app slot if no scope).
    session_id = str(uuid.uuid4())
    deep_link = (
        f"{settings.public_app_url.rstrip('/')}/dashboard"
        f"?voice=deep&scheduled_session_id={session_id}"
    )
    calendar = _get_calendar_service(settings, db)
    label = body.session_type.replace("_", " ").title()
    event_id, meet_url = await calendar.create_event(
        candidate_id=str(candidate["id"]),
        start_iso=start_dt.isoformat(),
        end_iso=end_dt.isoformat(),
        summary=f"Hireschema · {label} with Aarya",
        description=f"Your private 15-minute in-app call with Aarya. Start here: {deep_link}",
        attendee_email=current_user["email"],
    )

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
    if event_id:
        msg += " — reminder added to your Google Calendar. The call happens in Hireschema."
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
                "Connect Google Calendar in Settings to add future call reminders to your calendar."
            )
            msg += " " + google_hint
        else:
            google_hint = "Reconnect Google and grant calendar access for future reminders."
            msg += " " + google_hint
        calendar_connected = False

    return BookSessionResponse(
        session_id=session_id,
        calendar_event_id=event_id,
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        meet_url=None,
        message=msg,
        calendar_connected=calendar_connected,
        google_connect_hint=google_hint,
    )


@router.post("/start", response_model=CareerCallResponse, status_code=200)
async def start_career_call(
    body: StartCareerCallRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> CareerCallResponse:
    """Start an owned, consented career call using one durable session row."""
    if not body.consent:
        raise HTTPException(status_code=400, detail="Consent is required for a career call")

    user_id = uuid.UUID(current_user["id"])
    try:
        async with db.transaction():
            candidate = await db.fetchrow(
                "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
                user_id,
            )
            if not candidate:
                raise HTTPException(status_code=404, detail="Candidate profile not found")
            candidate_id = candidate["id"]

            conversation = await db.fetchrow(
                """
                SELECT id FROM public.conversations
                WHERE id = $1::uuid AND candidate_id = $2::uuid AND deleted_at IS NULL
                """,
                body.conversation_id,
                candidate_id,
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

            active = await db.fetchrow(
                """
                SELECT id, conversation_id, status, scheduled_at, started_at
                FROM public.voice_sessions
                WHERE candidate_id = $1::uuid
                  AND session_type = 'career_chat' AND status = 'active'
                LIMIT 1
                """,
                candidate_id,
            )
            if active:
                if active["conversation_id"] == body.conversation_id:
                    return _career_call_response(active)
                raise HTTPException(status_code=409, detail="Another career call is already active")

            started_at = datetime.now(UTC)
            if body.scheduled_session_id:
                scheduled = await db.fetchrow(
                    """
                    SELECT id, conversation_id, status, scheduled_at, started_at
                    FROM public.voice_sessions
                    WHERE id = $1::uuid AND candidate_id = $2::uuid
                      AND session_type = 'career_chat' AND status = 'scheduled'
                    FOR UPDATE
                    """,
                    body.scheduled_session_id,
                    candidate_id,
                )
                if not scheduled:
                    raced_active = await db.fetchrow(
                        """
                        SELECT id, conversation_id, status, scheduled_at, started_at
                        FROM public.voice_sessions
                        WHERE candidate_id = $1::uuid
                          AND session_type = 'career_chat' AND status = 'active'
                        LIMIT 1
                        """,
                        candidate_id,
                    )
                    if raced_active and raced_active["conversation_id"] == body.conversation_id:
                        return _career_call_response(raced_active)
                    if raced_active:
                        raise HTTPException(
                            status_code=409,
                            detail="Another career call is already active",
                        )
                    raise HTTPException(status_code=404, detail="Scheduled career call not found")
                session_id = scheduled["id"]
                scheduled_at = scheduled["scheduled_at"]
                await db.execute(
                    """
                    UPDATE public.voice_sessions
                    SET status = 'active', conversation_id = $3::uuid,
                        consent_version = $4, started_at = NOW(), updated_at = NOW()
                    WHERE id = $1::uuid AND candidate_id = $2::uuid
                    """,
                    session_id,
                    candidate_id,
                    body.conversation_id,
                    body.consent_version,
                )
            else:
                session_id = uuid.uuid4()
                scheduled_at = None
                await db.execute(
                    """
                    INSERT INTO public.voice_sessions (
                      id, candidate_id, conversation_id, session_type, status,
                      consent_version, started_at
                    )
                    VALUES ($1, $2, $3, 'career_chat', 'active', $4, NOW())
                    """,
                    session_id,
                    candidate_id,
                    body.conversation_id,
                    body.consent_version,
                )

            await db.execute(
                """
                INSERT INTO public.consent_log (user_id, purpose, granted)
                VALUES ($1, $2, TRUE)
                """,
                user_id,
                f"voice_career_discovery:{body.consent_version}",
            )
            coverage = CareerInterviewCoverage(
                current_focus=InterviewTopic.CURRENT_WORK,
                question_history=[InterviewTopic.CURRENT_WORK],
            )
            await db.execute(
                """
                INSERT INTO public.career_interview_states (session_id, candidate_id, state)
                VALUES ($1, $2, $3::jsonb)
                """,
                session_id,
                candidate_id,
                coverage.model_dump_json(),
            )
            return CareerCallResponse(
                id=str(session_id),
                conversation_id=str(body.conversation_id),
                status="active",
                scheduled_at=_isoformat(scheduled_at),
                started_at=started_at.isoformat(),
            )
    except asyncpg.UniqueViolationError as exc:
        active = await db.fetchrow(
            """
            SELECT vs.id, vs.conversation_id, vs.status, vs.scheduled_at, vs.started_at
            FROM public.voice_sessions vs
            JOIN public.candidates c ON c.id = vs.candidate_id
            WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
              AND vs.session_type = 'career_chat' AND vs.status = 'active'
            LIMIT 1
            """,
            user_id,
        )
        if active and active["conversation_id"] == body.conversation_id:
            return _career_call_response(active)
        raise HTTPException(
            status_code=409, detail="Another career call is already active"
        ) from exc


async def _complete_owned_career_call(
    *,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: CompleteCareerCallRequest,
    db: asyncpg.Connection,
) -> CareerCallResponse:
    """Complete one locked career call without deriving or publishing profile facts."""
    async with db.transaction():
        row = await db.fetchrow(
            """
            SELECT id, conversation_id, status, scheduled_at, started_at,
                   duration_secs, completion_reason
            FROM public.voice_sessions
            WHERE id = $1::uuid AND candidate_id = $2::uuid
              AND session_type = 'career_chat'
            FOR UPDATE
            """,
            session_id,
            candidate_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Career call not found")
        if row["status"] == "completed":
            if (
                row.get("duration_secs") == body.duration_seconds
                and row.get("completion_reason") == body.completion_reason
            ):
                return _career_call_response(row)
            raise HTTPException(status_code=409, detail="Career call was already completed")
        if row["status"] != "active":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot complete career call with status '{row['status']}'",
            )

        recap = await db.fetchrow(
            """
            SELECT content FROM public.messages
            WHERE conversation_id = $1::uuid AND role = 'assistant'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            row["conversation_id"],
        )
        summary = str(recap["content"]) if recap and recap.get("content") else None
        await db.execute(
            """
            UPDATE public.voice_sessions
            SET status = 'completed', ended_at = NOW(), duration_secs = $3,
                completion_reason = $4, summary = $5,
                transcript_version = transcript_version + 1, updated_at = NOW()
            WHERE id = $1::uuid AND candidate_id = $2::uuid AND status = 'active'
            """,
            session_id,
            candidate_id,
            body.duration_seconds,
            body.completion_reason,
            summary,
        )
        await db.execute(
            """
            UPDATE public.career_interview_states
            SET state = jsonb_set(state, '{completion_reason}', to_jsonb($3::text), TRUE),
                state_version = state_version + 1, updated_at = NOW()
            WHERE session_id = $1::uuid AND candidate_id = $2::uuid
            """,
            session_id,
            candidate_id,
            body.completion_reason,
        )
        return CareerCallResponse(
            id=str(session_id),
            conversation_id=str(row["conversation_id"]),
            status="completed",
            scheduled_at=_isoformat(row.get("scheduled_at")),
            started_at=_isoformat(row.get("started_at")),
        )


@router.post("/{session_id}/complete", response_model=CareerCallResponse, status_code=200)
async def complete_career_call(
    session_id: uuid.UUID,
    body: CompleteCareerCallRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> CareerCallResponse:
    """Complete an owned active career call without mutating public profile data."""
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return await _complete_owned_career_call(
        session_id=session_id,
        candidate_id=candidate["id"],
        body=body,
        db=db,
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
