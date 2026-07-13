"""
Intro handshake routes — candidate-facing intro request management.

POST /api/v1/intros                     → create candidate intro request
GET  /api/v1/intros                     → list candidate's intro requests
GET  /api/v1/intros/{id}                → single intro detail (+ draft email preview)
POST /api/v1/intros/{id}/cancel         → candidate cancels a pending intro
POST /api/v1/intros/{id}/approve-send   → candidate approves draft + triggers send
POST /api/v1/intros/{id}/approve-send-followup → approve 72h bump draft
POST /api/v1/intros/{id}/thankyou-draft → create/regenerate thank-you draft
POST /api/v1/intros/{id}/approve-send-thankyou → send thank-you via Gmail
PATCH /api/v1/intros/{id}/followup-draft / thankyou-draft → edit draft bodies

Nitya writes to intro_requests via its own DB connection (not via HTTP).
Aarya creates intro_requests via the tools.request_intro() function.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.services.display_name import sanitize_display_name
from hireloop_api.services.intro_outbound import (
    _parse_draft,
    ensure_thankyou_draft,
    thankyou_draft_bodies,
)
from hireloop_api.services.intro_service import create_candidate_intro

logger = structlog.get_logger()
router = APIRouter(prefix="/intros", tags=["intros"])


# ── Models ────────────────────────────────────────────────────────────────────


class IntroSummary(BaseModel):
    id: str
    job_id: str
    job_title: str
    company_name: str | None
    hm_name: str
    hm_title: str | None
    direction: str | None = None
    status: str
    created_at: str
    sent_at: str | None
    opened_at: str | None
    replied_at: str | None
    followup_ready: bool = False
    thankyou_ready: bool = False
    thankyou_sent: bool = False
    nudged_at: str | None = None


class IntroDetail(IntroSummary):
    draft_email: str | None  # JSON string with {subject, body_html, body_text}
    error_message: str | None
    gmail_connected: bool
    hm_email: str | None = None
    followup_draft_email: str | None = None
    followup_draft_at: str | None = None
    thankyou_draft_email: str | None = None
    thankyou_draft_at: str | None = None
    thankyou_sent_at: str | None = None
    gmail_thread_id: str | None = None


class CreateIntroRequest(BaseModel):
    job_id: uuid.UUID
    hiring_manager_id: uuid.UUID | None = None
    message: str | None = None


class DraftEditRequest(BaseModel):
    subject: str | None = None
    body_html: str | None = None
    body_text: str | None = Field(default=None, max_length=20000)

# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_intro(
    body: CreateIntroRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Create a candidate intro request without relying on chat tool execution."""
    result = await create_candidate_intro(
        db,
        user_id=current_user["id"],
        job_id=str(body.job_id),
        hiring_manager_id=str(body.hiring_manager_id) if body.hiring_manager_id else None,
        message=body.message,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=str(result["error"]))
    return result


@router.get("", response_model=list[IntroSummary])
async def list_intros(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List all intro requests for the current candidate."""
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    rows = await db.fetch(
        """
        SELECT
            ir.id, ir.status, ir.direction, ir.created_at, ir.sent_at, ir.opened_at, ir.replied_at,
            ir.followup_draft_at, ir.nudged_at, ir.thankyou_draft_at, ir.thankyou_sent_at,
            j.id AS job_id, j.title AS job_title,
            co.name AS company_name,
            COALESCE(hm.full_name, ru.full_name) AS hm_name,
            COALESCE(hm.title, rec.title) AS hm_title
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        LEFT JOIN public.recruiters rec ON rec.id = ir.recruiter_id
        LEFT JOIN public.users ru ON ru.id = rec.user_id
        WHERE ir.candidate_id = $1::uuid
        ORDER BY ir.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        candidate["id"],
        limit,
        offset,
    )

    return [_summary_to_dict(r) for r in rows]


@router.get("/{intro_id}", response_model=IntroDetail)
async def get_intro(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Get full intro request detail including draft email preview."""
    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    row = await db.fetchrow(
        """
        SELECT
            ir.id, ir.status, ir.direction, ir.draft_email, ir.error_message,
            ir.created_at, ir.sent_at, ir.opened_at, ir.replied_at,
            ir.followup_draft_email, ir.followup_draft_at, ir.nudged_at,
            ir.thankyou_draft_email, ir.thankyou_draft_at, ir.thankyou_sent_at,
            ir.gmail_thread_id,
            j.id AS job_id, j.title AS job_title,
            co.name AS company_name,
            COALESCE(hm.full_name, ru.full_name) AS hm_name,
            COALESCE(hm.title, rec.title) AS hm_title,
            hm.email AS hm_email
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        LEFT JOIN public.recruiters rec ON rec.id = ir.recruiter_id
        LEFT JOIN public.users ru ON ru.id = rec.user_id
        WHERE ir.id = $1::uuid AND ir.candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )

    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")

    # Check if candidate has Gmail connected
    gmail_row = await db.fetchrow(
        "SELECT id FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
        candidate["id"],
    )

    d = _summary_to_dict(row)
    d["draft_email"] = row["draft_email"]
    d["error_message"] = row["error_message"]
    d["gmail_connected"] = gmail_row is not None
    d["hm_email"] = row["hm_email"]
    d["followup_draft_email"] = row["followup_draft_email"]
    d["followup_draft_at"] = (
        row["followup_draft_at"].isoformat() if row["followup_draft_at"] else None
    )
    d["thankyou_draft_email"] = row["thankyou_draft_email"]
    d["thankyou_draft_at"] = (
        row["thankyou_draft_at"].isoformat() if row["thankyou_draft_at"] else None
    )
    d["thankyou_sent_at"] = (
        row["thankyou_sent_at"].isoformat() if row["thankyou_sent_at"] else None
    )
    d["gmail_thread_id"] = row["gmail_thread_id"]
    return d


def _normalize_intro_status(status: str) -> str:
    if status == "drafting":
        return "draft_ready"
    return status


@router.post("/{intro_id}/approve-send", status_code=200)
async def approve_and_send_intro(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate approves Nitya's draft and triggers Gmail send (R9)."""
    from hireloop_api.agents.nitya import tools as nitya_tools
    from hireloop_api.config import get_settings

    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    row = await db.fetchrow(
        """
        SELECT ir.id, ir.status, ir.draft_email, ir.direction,
               hm.email AS hm_email, hm.full_name AS hm_name
        FROM public.intro_requests ir
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        WHERE ir.id = $1::uuid AND ir.candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")
    if row["direction"] != "candidate_to_hm":
        raise HTTPException(status_code=409, detail="Only HM email intros support approve-send")
    if row["status"] not in ("draft_ready", "drafting"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot send intro in status '{row['status']}'",
        )

    draft_raw = row["draft_email"]
    if not draft_raw:
        raise HTTPException(status_code=409, detail="No draft email to send")
    import json as _json

    draft = _json.loads(draft_raw) if isinstance(draft_raw, str) else draft_raw
    settings = get_settings()
    send_result = await nitya_tools.send_intro_email(
        db=db,
        user_id=str(current_user["id"]),
        session_id=intro_id,
        intro_id=intro_id,
        candidate_id=str(candidate["id"]),
        hm_email=row["hm_email"],
        hm_name=row["hm_name"] or "Hiring Manager",
        subject=draft.get("subject", "Introduction"),
        body_html=draft.get("body_html", ""),
        body_text=draft.get("body_text", ""),
        google_client_id=settings.google_client_id,
        google_client_secret=settings.google_client_secret,
    )
    if not send_result.get("sent"):
        raise HTTPException(
            status_code=502,
            detail=send_result.get("error", "Failed to send intro email"),
        )
    return {"intro_id": intro_id, "status": "sent", "sent": True}


@router.post("/{intro_id}/cancel", status_code=200)
async def cancel_intro(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Cancel a pending intro request."""
    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    result = await db.execute(
        """
        UPDATE public.intro_requests
        SET status = 'cancelled', updated_at = NOW()
        WHERE id = $1::uuid
          AND candidate_id = $2::uuid
          AND status IN ('pending', 'enriching', 'drafting', 'draft_ready')
        """,
        intro_uuid,
        candidate["id"],
    )

    if result == "UPDATE 0":
        raise HTTPException(
            status_code=409,
            detail="Cannot cancel — intro has already been sent or is not yours",
        )

    return {"cancelled": True, "intro_id": intro_id}


@router.post("/{intro_id}/mark-replied", status_code=200)
async def mark_intro_replied(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate confirms the hiring manager replied to their intro email.

    Manual by design: Gmail access is send-only (we never read candidate
    email), so the candidate is the reply detector. This is what makes the
    intro→conversation funnel measurable.
    """
    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    result = await db.execute(
        """
        UPDATE public.intro_requests
        SET status = 'replied', replied_at = NOW(), updated_at = NOW()
        WHERE id = $1::uuid
          AND candidate_id = $2::uuid
          AND status IN ('sent', 'opened')
        """,
        intro_uuid,
        candidate["id"],
    )
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=409,
            detail="Intro is not in a sent state (or is not yours).",
        )

    from hireloop_api.config import get_settings

    settings = get_settings()
    await ensure_thankyou_draft(db, intro_id=intro_id, settings=settings, notify=True)
    return {"replied": True, "intro_id": intro_id}


@router.post("/{intro_id}/respond", status_code=200)
async def respond_to_intro(
    intro_id: str,
    accept: bool = True,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate accepts or declines a recruiter→candidate intro request."""
    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    new_status = "accepted" if accept else "declined"
    result = await db.execute(
        """
        UPDATE public.intro_requests
        SET status = $3, updated_at = NOW()
        WHERE id = $1::uuid
          AND candidate_id = $2::uuid
          AND direction = 'recruiter_to_candidate'
          AND status = 'pending'
        """,
        intro_uuid,
        candidate["id"],
        new_status,
    )
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=409,
            detail="Nothing to respond to — intro is not a pending recruiter request.",
        )

    from hireloop_api.config import get_settings
    from hireloop_api.services.notifications import notify_intro_lifecycle

    settings = get_settings()
    intro = await db.fetchrow(
        """
        SELECT j.title AS job_title, co.name AS company_name,
               ru.full_name AS recruiter_name
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        JOIN public.recruiters rec ON rec.id = ir.recruiter_id
        JOIN public.users ru ON ru.id = rec.user_id
        WHERE ir.id = $1::uuid
        """,
        intro_uuid,
    )
    await notify_intro_lifecycle(
        db,
        settings,
        intro_id=intro_id,
        event=new_status,
        recipient_user_id=str(current_user["id"]),
        title=f"Intro {new_status}",
        body=f"Your response was recorded for {intro['job_title'] if intro else 'the role'}.",
        email_template_data={
            "full_name": current_user.get("full_name") or "there",
            "hm_name": intro["recruiter_name"] if intro else "the recruiter",
            "company_name": (intro["company_name"] if intro else None) or "the company",
            "job_title": (intro["job_title"] if intro else None) or "the role",
            "status": new_status,
            "status_message": f"Intro {new_status}.",
            "cta_url": f"{settings.allowed_origins[0] if settings.allowed_origins else 'https://hireschema.com'}/intros",
        },
    )
    return {"intro_id": intro_id, "status": new_status}


async def _require_candidate(db: asyncpg.Connection, user_id: str) -> asyncpg.Record:
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def _merge_draft(existing: dict[str, str] | None, body: DraftEditRequest) -> dict[str, str]:
    base = existing or {"subject": "", "body_html": "", "body_text": ""}
    if body.subject is not None:
        base["subject"] = body.subject
    if body.body_html is not None:
        base["body_html"] = body.body_html
    if body.body_text is not None:
        base["body_text"] = body.body_text
        if body.body_html is None:
            base["body_html"] = (
                "<p>" + body.body_text.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
            )
    return base


@router.patch("/{intro_id}/followup-draft", status_code=200)
async def patch_followup_draft(
    intro_id: str,
    body: DraftEditRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate edits the pending follow-up draft before approve-send."""
    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc
    candidate = await _require_candidate(db, current_user["id"])
    row = await db.fetchrow(
        """
        SELECT followup_draft_email, followup_draft_at, nudged_at
        FROM public.intro_requests
        WHERE id = $1::uuid AND candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")
    if row["nudged_at"] is not None:
        raise HTTPException(status_code=409, detail="Follow-up already sent")
    if row["followup_draft_at"] is None:
        raise HTTPException(status_code=409, detail="No follow-up draft to edit")
    merged = _merge_draft(_parse_draft(row["followup_draft_email"]), body)
    await db.execute(
        """
        UPDATE public.intro_requests
        SET followup_draft_email = $2::text, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        intro_uuid,
        json.dumps(merged),
    )
    return {"intro_id": intro_id, "followup_draft_email": merged}


@router.post("/{intro_id}/approve-send-followup", status_code=200)
async def approve_and_send_followup(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate approves the 72h bump and sends it in the same Gmail thread."""
    from hireloop_api.config import get_settings
    from hireloop_api.services.email.gmail_oauth import GmailOAuthService

    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc
    candidate = await _require_candidate(db, current_user["id"])
    row = await db.fetchrow(
        """
        SELECT ir.followup_draft_email, ir.followup_draft_at, ir.nudged_at,
               ir.gmail_thread_id, ir.gmail_subject, ir.status,
               hm.email AS hm_email, hm.full_name AS hm_name
        FROM public.intro_requests ir
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        WHERE ir.id = $1::uuid AND ir.candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")
    if row["nudged_at"] is not None:
        raise HTTPException(status_code=409, detail="Follow-up already sent")
    if row["followup_draft_at"] is None or not row["followup_draft_email"]:
        raise HTTPException(status_code=409, detail="No follow-up draft to send")
    if not row["gmail_thread_id"]:
        raise HTTPException(status_code=409, detail="Missing Gmail thread for follow-up")
    if not row["hm_email"]:
        raise HTTPException(status_code=409, detail="Hiring manager email missing")

    draft = _parse_draft(row["followup_draft_email"])
    if not draft:
        raise HTTPException(status_code=409, detail="Follow-up draft is invalid")
    subject = draft.get("subject") or row["gmail_subject"] or "Follow-up"
    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Gmail OAuth is not configured")

    svc = GmailOAuthService(
        google_client_id=settings.google_client_id,
        google_client_secret=settings.google_client_secret,
        db=db,
    )
    try:
        ok, info = await svc.send_intro_email(
            candidate_id=str(candidate["id"]),
            to_email=row["hm_email"],
            to_name=row["hm_name"] or "",
            subject=subject,
            body_html=draft.get("body_html") or "",
            body_text=draft.get("body_text"),
            thread_id=row["gmail_thread_id"],
        )
    finally:
        await svc.close()

    if not ok:
        raise HTTPException(status_code=502, detail=str(info) if info else "Gmail send failed")

    await db.execute(
        """
        UPDATE public.intro_requests
        SET nudged_at = NOW(),
            followup_draft_email = NULL,
            updated_at = NOW()
        WHERE id = $1::uuid
        """,
        intro_uuid,
    )
    return {"intro_id": intro_id, "sent": True, "nudged": True}


@router.post("/{intro_id}/thankyou-draft", status_code=200)
async def create_thankyou_draft(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Manual thank-you draft (or regenerate if not yet sent)."""
    from hireloop_api.config import get_settings

    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc
    candidate = await _require_candidate(db, current_user["id"])
    row = await db.fetchrow(
        """
        SELECT ir.status, ir.thankyou_sent_at, ir.thankyou_draft_at,
               j.title AS job_title, co.name AS company_name,
               hm.full_name AS hm_name, u.full_name AS candidate_name
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE ir.id = $1::uuid AND ir.candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")
    if row["thankyou_sent_at"] is not None:
        raise HTTPException(status_code=409, detail="Thank-you already sent")
    if row["status"] not in ("sent", "opened", "replied", "accepted"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot draft thank-you in status '{row['status']}'",
        )

    settings = get_settings()
    if row["thankyou_draft_at"] is None:
        created = await ensure_thankyou_draft(
            db, intro_id=intro_id, settings=settings, notify=False
        )
        if not created:
            raise HTTPException(status_code=409, detail="Could not create thank-you draft")
    else:
        # Regenerate content while keeping draft_at
        draft = thankyou_draft_bodies(
            row["hm_name"] or "",
            row["job_title"] or "",
            row["candidate_name"] or "",
            row["company_name"],
        )
        await db.execute(
            """
            UPDATE public.intro_requests
            SET thankyou_draft_email = $2::text, updated_at = NOW()
            WHERE id = $1::uuid AND thankyou_sent_at IS NULL
            """,
            intro_uuid,
            json.dumps(draft),
        )
    detail = await db.fetchval(
        "SELECT thankyou_draft_email FROM public.intro_requests WHERE id = $1::uuid",
        intro_uuid,
    )
    return {"intro_id": intro_id, "thankyou_draft_email": _parse_draft(detail)}


@router.patch("/{intro_id}/thankyou-draft", status_code=200)
async def patch_thankyou_draft(
    intro_id: str,
    body: DraftEditRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc
    candidate = await _require_candidate(db, current_user["id"])
    row = await db.fetchrow(
        """
        SELECT thankyou_draft_email, thankyou_draft_at, thankyou_sent_at
        FROM public.intro_requests
        WHERE id = $1::uuid AND candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")
    if row["thankyou_sent_at"] is not None:
        raise HTTPException(status_code=409, detail="Thank-you already sent")
    if row["thankyou_draft_at"] is None:
        raise HTTPException(status_code=409, detail="No thank-you draft to edit")
    merged = _merge_draft(_parse_draft(row["thankyou_draft_email"]), body)
    await db.execute(
        """
        UPDATE public.intro_requests
        SET thankyou_draft_email = $2::text, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        intro_uuid,
        json.dumps(merged),
    )
    return {"intro_id": intro_id, "thankyou_draft_email": merged}


@router.post("/{intro_id}/approve-send-thankyou", status_code=200)
async def approve_and_send_thankyou(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate approves and sends thank-you via Gmail (same thread when possible)."""
    from hireloop_api.config import get_settings
    from hireloop_api.services.email.gmail_oauth import GmailOAuthService

    try:
        intro_uuid = uuid.UUID(intro_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid intro ID") from exc
    candidate = await _require_candidate(db, current_user["id"])
    row = await db.fetchrow(
        """
        SELECT ir.thankyou_draft_email, ir.thankyou_draft_at, ir.thankyou_sent_at,
               ir.gmail_thread_id,
               hm.email AS hm_email, hm.full_name AS hm_name
        FROM public.intro_requests ir
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        WHERE ir.id = $1::uuid AND ir.candidate_id = $2::uuid
        """,
        intro_uuid,
        candidate["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Intro request not found")
    if row["thankyou_sent_at"] is not None:
        raise HTTPException(status_code=409, detail="Thank-you already sent")
    if row["thankyou_draft_at"] is None or not row["thankyou_draft_email"]:
        raise HTTPException(status_code=409, detail="No thank-you draft to send")
    if not row["hm_email"]:
        raise HTTPException(status_code=409, detail="Hiring manager email missing")

    draft = _parse_draft(row["thankyou_draft_email"])
    if not draft:
        raise HTTPException(status_code=409, detail="Thank-you draft is invalid")
    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Gmail OAuth is not configured")

    svc = GmailOAuthService(
        google_client_id=settings.google_client_id,
        google_client_secret=settings.google_client_secret,
        db=db,
    )
    try:
        ok, info = await svc.send_intro_email(
            candidate_id=str(candidate["id"]),
            to_email=row["hm_email"],
            to_name=row["hm_name"] or "",
            subject=draft.get("subject") or "Thank you",
            body_html=draft.get("body_html") or "",
            body_text=draft.get("body_text"),
            thread_id=row["gmail_thread_id"],
        )
    finally:
        await svc.close()

    if not ok:
        raise HTTPException(status_code=502, detail=str(info) if info else "Gmail send failed")

    await db.execute(
        """
        UPDATE public.intro_requests
        SET thankyou_sent_at = NOW(),
            thankyou_draft_email = NULL,
            updated_at = NOW()
        WHERE id = $1::uuid
        """,
        intro_uuid,
    )
    return {"intro_id": intro_id, "sent": True}


@router.get("/{intro_id}/messages")
async def list_intro_messages(
    intro_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate reads the direct chat thread for an intro."""
    from hireloop_api.services.intro_chat import list_messages

    try:
        return await list_messages(db, intro_id=intro_id, user_id=current_user["id"])
    except ValueError as e:
        raise HTTPException(404, str(e)) from None


@router.post("/{intro_id}/messages", status_code=201)
async def send_intro_message(
    intro_id: str,
    body: dict,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Candidate posts a message in an accepted intro thread."""
    from hireloop_api.services.intro_chat import post_message

    try:
        return await post_message(
            db, intro_id=intro_id, user_id=current_user["id"], body=body.get("body", "")
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except PermissionError as e:
        raise HTTPException(409, str(e)) from None


# ── Serialiser ────────────────────────────────────────────────────────────────


def _summary_to_dict(row: asyncpg.Record) -> dict:
    followup_at = row["followup_draft_at"] if "followup_draft_at" in row.keys() else None
    nudged_at = row["nudged_at"] if "nudged_at" in row.keys() else None
    thankyou_at = row["thankyou_draft_at"] if "thankyou_draft_at" in row.keys() else None
    thankyou_sent = row["thankyou_sent_at"] if "thankyou_sent_at" in row.keys() else None
    return {
        "id": str(row["id"]),
        "job_id": str(row["job_id"]),
        "job_title": row["job_title"],
        "company_name": row["company_name"],
        "hm_name": sanitize_display_name(row["hm_name"]) or row["hm_name"],
        "hm_title": row["hm_title"],
        "direction": row["direction"],
        "status": _normalize_intro_status(row["status"]),
        "created_at": row["created_at"].isoformat(),
        "sent_at": row["sent_at"].isoformat() if row["sent_at"] else None,
        "opened_at": row["opened_at"].isoformat() if row["opened_at"] else None,
        "replied_at": row["replied_at"].isoformat() if row["replied_at"] else None,
        "followup_ready": bool(followup_at) and not nudged_at,
        "thankyou_ready": bool(thankyou_at) and not thankyou_sent,
        "thankyou_sent": bool(thankyou_sent),
        "nudged_at": nudged_at.isoformat() if nudged_at else None,
    }
