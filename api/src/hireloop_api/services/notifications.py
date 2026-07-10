"""
Notification orchestration — in-app + WhatsApp (MSG91) + email (Resend).

Email templates live in ``notification_templates``; delivery respects
``users.notification_prefs`` category toggles (Settings → Notifications).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.email.notification_templates import (
    normalize_category,
    render_notification_email,
)
from hireloop_api.services.email.resend_service import ResendService
from hireloop_api.services.email.sendgrid_service import SendGridService
from hireloop_api.services.whatsapp.msg91 import Msg91Client, resolve_msg91_template_name

logger = structlog.get_logger()

MATCH_NOTIFY_MIN_SCORE = 0.65
JOB_MATCH_TEMPLATE = "job_match_alert"


def _app_base(settings: Settings) -> str:
    base = settings.public_app_url.rstrip("/") if settings.public_app_url else ""
    if base and "localhost" not in base:
        return base
    if settings.allowed_origins:
        for origin in settings.allowed_origins:
            if "hireschema" in origin or "3001" in origin:
                return origin.rstrip("/")
        return settings.allowed_origins[0].rstrip("/")
    return "https://www.hireschema.com"


def _email_provider_configured(settings: Settings) -> bool:
    return bool((settings.resend_api_key or "").strip())


def _sendgrid_usable(settings: Settings) -> bool:
    key = (settings.sendgrid_api_key or "").strip()
    if not key or len(key) < 24:
        return False
    if key in ("SG....", "SG...", "SG.."):
        return False
    return key.startswith("SG.")


async def _send_html(settings: Settings, *, to_email: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
        return False
    svc = ResendService(
        settings.resend_api_key, settings.resend_from_email, settings.resend_from_name
    )
    try:
        return await svc.send(to_email=to_email, subject=subject, html=html)
    finally:
        await svc.close()


def default_notification_prefs(*, marketing_emails: bool = True) -> dict[str, dict[str, bool]]:
    """Default opt-in matrix — matches Settings → Notifications categories."""
    default_on = {"email": True, "whatsapp": True}
    return {
        "job_match_alerts": dict(default_on),
        "intro_updates": dict(default_on),
        "interview_reminders": dict(default_on),
        "aarya_digest": dict(default_on),
        "profile_views": dict(default_on),
        "application_updates": dict(default_on),
        "platform_updates": {"email": marketing_emails, "whatsapp": False},
        # Legacy keys kept for older clients
        "intro_status": dict(default_on),
    }


async def ensure_default_notification_prefs(
    db: asyncpg.Connection,
    user_id: uuid.UUID | str,
) -> None:
    """Seed notification_prefs when empty so Settings toggles gate email delivery."""
    uid = uuid.UUID(str(user_id))
    row = await db.fetchrow(
        "SELECT notification_prefs FROM public.users WHERE id = $1 AND deleted_at IS NULL",
        uid,
    )
    if not row:
        return
    prefs = row["notification_prefs"]
    if isinstance(prefs, dict) and prefs:
        return
    await db.execute(
        """
        UPDATE public.users
        SET notification_prefs = $2::jsonb, updated_at = NOW()
        WHERE id = $1 AND deleted_at IS NULL
        """,
        uid,
        json.dumps(default_notification_prefs()),
    )


def _pref_channel_allowed(prefs: dict | None, category: str, channel: str) -> bool:
    """Default opt-in: missing prefs or missing channel → allowed."""
    if not prefs:
        return True
    cat = normalize_category(category)
    cat_prefs = prefs.get(cat) or {}
    if not isinstance(cat_prefs, dict):
        return True
    # Legacy nested keys
    if channel == "email" and cat_prefs.get("email") is False:
        return False
    if channel == "whatsapp" and cat_prefs.get("whatsapp") is False:
        return False
    return True


async def _log_whatsapp_send(
    db: asyncpg.Connection,
    *,
    user_id: str,
    phone: str,
    template_name: str,
    purpose: str,
    payload: dict,
    result: dict,
) -> None:
    status = "sent" if result.get("sent") else "failed"
    await db.execute(
        """
        INSERT INTO public.whatsapp_messages (
          user_id, template_name, purpose, phone, payload,
          external_message_id, status, error_message
        )
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6, $7, $8)
        """,
        user_id,
        template_name,
        purpose,
        phone,
        json.dumps(payload),
        str(result.get("message_id", "")),
        status,
        result.get("error"),
    )
    if result.get("sent"):
        await db.execute(
            """
            INSERT INTO public.consent_log (user_id, purpose, granted)
            VALUES ($1::uuid, $2, TRUE)
            """,
            user_id,
            f"whatsapp_{purpose}",
        )


async def send_category_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
    category: str,
    to_email: str,
    to_name: str | None,
    template_data: dict[str, Any],
    template_id: str = "",
) -> dict[str, Any]:
    """Send a category email via Resend when prefs + provider allow."""
    if not to_email:
        return {"sent": False, "skipped": "no_email"}

    user = await db.fetchrow(
        "SELECT notification_prefs FROM public.users WHERE id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not user:
        return {"sent": False, "error": "User not found"}

    cat = normalize_category(category)
    prefs = user["notification_prefs"] or {}
    if not _pref_channel_allowed(prefs, cat, "email"):
        return {"sent": False, "skipped": "opted_out"}

    data = {**template_data, "full_name": template_data.get("full_name") or to_name or "there"}
    if "cta_url" not in data:
        data["cta_url"] = f"{_app_base(settings)}/dashboard"

    subject, html = render_notification_email(cat, data)

    if _email_provider_configured(settings):
        sent = await _send_html(settings, to_email=to_email, subject=subject, html=html)
        if sent:
            return {"sent": True, "provider": "resend"}

    if _sendgrid_usable(settings) and template_id:
        svc = SendGridService(
            settings.sendgrid_api_key,
            settings.sendgrid_from_email,
            settings.sendgrid_from_name,
        )
        try:
            sent = await svc._send(
                to_email=to_email,
                to_name=to_name,
                template_id=template_id,
                dynamic_data=data,
            )
            return {"sent": bool(sent), "provider": "sendgrid"}
        finally:
            await svc.close()

    return {"sent": False, "skipped": "email_unconfigured"}


async def send_email_if_allowed(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
    purpose: str,
    to_email: str,
    to_name: str | None,
    template_id: str,
    dynamic_data: dict[str, Any],
) -> dict[str, Any]:
    """Backward-compatible wrapper — prefers Resend HTML templates."""
    return await send_category_email(
        db,
        settings,
        user_id=user_id,
        category=purpose,
        to_email=to_email,
        to_name=to_name,
        template_data=dynamic_data,
        template_id=template_id,
    )


async def _log_in_app(
    db: asyncpg.Connection,
    *,
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    data: dict[str, Any],
    channels: list[str],
) -> None:
    await db.execute(
        """
        INSERT INTO public.notifications (user_id, type, title, body, data, channels, sent_at)
        VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6::text[], NOW())
        """,
        uuid.UUID(user_id),
        notif_type,
        title,
        body,
        json.dumps(data),
        channels,
    )


async def notify_intro_status_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    intro_id: str,
    status: str,
) -> dict[str, Any]:
    """Email candidate when their intro status changes."""
    if status not in ("sent", "opened", "replied"):
        return {"sent": False, "skipped": "status_not_notifiable"}

    row = await db.fetchrow(
        """
        SELECT u.id AS user_id, u.email, u.full_name,
               j.title AS job_title, co.name AS company_name,
               hm.full_name AS hm_name
        FROM public.intro_requests ir
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users u ON u.id = c.user_id
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        WHERE ir.id = $1::uuid
        """,
        uuid.UUID(intro_id),
    )
    if not row or not row["email"]:
        return {"sent": False, "error": "No candidate email on file"}

    app_base = _app_base(settings)
    return await send_category_email(
        db,
        settings,
        user_id=str(row["user_id"]),
        category="intro_updates",
        to_email=row["email"],
        to_name=row["full_name"],
        template_data={
            "full_name": row["full_name"] or "there",
            "hm_name": row["hm_name"] or "the hiring manager",
            "company_name": row["company_name"] or "the company",
            "job_title": row["job_title"] or "the role",
            "status": status,
            "status_message": {
                "sent": f"Your intro to {row['hm_name'] or 'the hiring manager'} has been sent!",
                "opened": f"{row['hm_name'] or 'The hiring manager'} opened your intro email.",
                "replied": f"{row['hm_name'] or 'The hiring manager'} replied to your intro!",
            }.get(status, f"Intro status: {status}"),
            "cta_url": f"{app_base}/dashboard",
        },
        template_id=settings.sg_template_intro_status,
    )


async def send_whatsapp_if_allowed(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
    template_name: str,
    purpose: str,
    body_params: list[str],
) -> dict[str, Any]:
    """Send WhatsApp template when user prefs allow."""
    user = await db.fetchrow(
        "SELECT phone, notification_prefs FROM public.users WHERE id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not user or not user["phone"]:
        return {"sent": False, "error": "No phone on file"}

    prefs = user["notification_prefs"] or {}
    cat = normalize_category(purpose)
    if not _pref_channel_allowed(prefs, cat, "whatsapp"):
        return {"sent": False, "skipped": "opted_out"}

    wa = Msg91Client(
        settings.msg91_auth_key,
        sender_id=settings.msg91_sender_id,
        whatsapp_number=settings.msg91_whatsapp_number,
    )
    template_name = resolve_msg91_template_name(settings, template_name)
    try:
        result = await wa.send_whatsapp_template(
            to_phone=user["phone"],
            template_name=template_name,
            body_params=body_params,
        )
    finally:
        await wa.close()

    await _log_whatsapp_send(
        db,
        user_id=user_id,
        phone=user["phone"],
        template_name=template_name,
        purpose=cat,
        payload={"body_params": body_params},
        result=result,
    )
    return result


async def _already_notified(
    db: asyncpg.Connection,
    *,
    user_id: str,
    notif_type: str,
    dedupe_key: str,
    within_hours: int = 24,
) -> bool:
    row = await db.fetchrow(
        """
        SELECT 1 FROM public.notifications
        WHERE user_id = $1::uuid
          AND type = $2
          AND data->>'dedupe_key' = $3
          AND created_at > NOW() - make_interval(hours => $4)
        LIMIT 1
        """,
        uuid.UUID(user_id),
        notif_type,
        dedupe_key,
        within_hours,
    )
    return row is not None


async def notify_job_match(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    candidate_id: str,
    job_id: str,
    overall_score: float,
    job_title: str,
    company_name: str | None,
) -> None:
    """In-app + email (Resend) + WhatsApp when a strong new match is computed."""
    if overall_score < MATCH_NOTIFY_MIN_SCORE:
        return

    row = await db.fetchrow(
        """
        SELECT c.user_id, u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    if not row:
        return

    user_id = str(row["user_id"])
    dedupe_key = f"job:{job_id}"
    if await _already_notified(db, user_id=user_id, notif_type="job_match", dedupe_key=dedupe_key):
        return

    app_base = _app_base(settings)
    deep_link = f"{app_base}/dashboard?job={job_id}"
    pct = round(overall_score * 100)
    title = job_title
    company = company_name or "a company"
    notif_body = f"{title} at {company} — {pct}% match"
    data = {
        "job_id": job_id,
        "deep_link": deep_link,
        "score": overall_score,
        "dedupe_key": dedupe_key,
    }

    channels = ["in_app"]
    first_job_email_sent = False
    if row["email"]:
        match_count = await db.fetchval(
            """
            SELECT count(*)::int FROM public.match_scores
            WHERE candidate_id = $1::uuid AND overall_score >= $2
            """,
            uuid.UUID(candidate_id),
            MATCH_NOTIFY_MIN_SCORE,
        )
        if match_count == 1:
            from hireloop_api.services.email.lifecycle_emails import send_first_job_found_email

            first_result = await send_first_job_found_email(
                db,
                settings,
                candidate_id=candidate_id,
                job_id=job_id,
                job_title=title,
                company_name=company_name,
                overall_score=overall_score,
            )
            if first_result.get("sent"):
                channels.append("email")
                first_job_email_sent = True

        if not first_job_email_sent:
            email_result = await send_category_email(
                db,
                settings,
                user_id=user_id,
                category="job_match_alerts",
                to_email=row["email"],
                to_name=row["full_name"],
                template_data={
                    "full_name": row["full_name"] or "there",
                    "job_title": title,
                    "company_name": company,
                    "score_pct": pct,
                    "cta_url": deep_link,
                },
                template_id=settings.sg_template_job_match_alert,
            )
            if email_result.get("sent"):
                channels.append("email")

    wa_result = await send_whatsapp_if_allowed(
        db,
        settings,
        user_id=user_id,
        template_name=JOB_MATCH_TEMPLATE,
        purpose="job_match_alerts",
        body_params=[row["full_name"] or "there", title, company, str(pct), deep_link],
    )
    if wa_result.get("sent"):
        channels.append("whatsapp")

    await _log_in_app(
        db,
        user_id=user_id,
        notif_type="job_match",
        title="New job match",
        body=notif_body,
        data=data,
        channels=channels,
    )
    logger.info(
        "job_match_notified", user_id=user_id, job_id=job_id, score=overall_score, channels=channels
    )


async def notify_intro_lifecycle(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    intro_id: str,
    event: str,
    recipient_user_id: str,
    title: str,
    body: str,
    email_template_data: dict[str, Any] | None = None,
) -> None:
    """In-app + optional email/WhatsApp when an intro changes state."""
    channels: list[str] = ["in_app"]
    data = {"intro_id": intro_id, "event": event, "dedupe_key": f"intro:{intro_id}:{event}"}

    user = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(recipient_user_id),
    )
    if user and user["email"] and email_template_data:
        tpl = {
            **email_template_data,
            "full_name": email_template_data.get("full_name") or user["full_name"],
        }
        email_result = await send_category_email(
            db,
            settings,
            user_id=recipient_user_id,
            category="intro_updates",
            to_email=user["email"],
            to_name=user["full_name"],
            template_data=tpl,
            template_id=settings.sg_template_intro_status,
        )
        if email_result.get("sent"):
            channels.append("email")

    if settings.msg91_intro_status_template:
        wa_result = await send_whatsapp_if_allowed(
            db,
            settings,
            user_id=recipient_user_id,
            template_name="intro_status",
            purpose="intro_updates",
            body_params=[title, body[:120]],
        )
        if wa_result.get("sent"):
            channels.append("whatsapp")

    await _log_in_app(
        db,
        user_id=recipient_user_id,
        notif_type="intro_status",
        title=title,
        body=body,
        data=data,
        channels=channels,
    )


async def notify_interview_booked(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
    session_id: str,
    session_type: str,
    scheduled_at: datetime,
) -> None:
    """Confirmation email when a voice session is booked."""
    user = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not user or not user["email"]:
        return

    label = session_type.replace("_", " ").title()
    when = scheduled_at.astimezone(UTC).strftime("%a %d %b %Y, %H:%M UTC")
    app_base = _app_base(settings)
    channels = ["in_app"]
    email_result = await send_category_email(
        db,
        settings,
        user_id=user_id,
        category="interview_reminders",
        to_email=user["email"],
        to_name=user["full_name"],
        template_data={
            "full_name": user["full_name"] or "there",
            "session_label": label,
            "scheduled_label": when,
            "scheduled_at": when,
            "is_reminder": False,
            "cta_url": f"{app_base}/dashboard",
        },
        template_id=settings.sg_template_interview_reminder,
    )
    if email_result.get("sent"):
        channels.append("email")

    await _log_in_app(
        db,
        user_id=user_id,
        notif_type="interview_booked",
        title=f"{label} booked",
        body=f"Scheduled for {when}",
        data={"session_id": session_id, "dedupe_key": f"booked:{session_id}"},
        channels=channels,
    )

    # Schedule 24h-before reminder when far enough in the future.
    reminder_at = scheduled_at - timedelta(hours=24)
    if reminder_at > datetime.now(UTC):
        from hireloop_api.services.background_jobs import INTERVIEW_REMINDER, enqueue_job

        await enqueue_job(
            db,
            kind=INTERVIEW_REMINDER,
            payload={
                "user_id": user_id,
                "session_id": session_id,
                "session_type": session_type,
                "scheduled_at": scheduled_at.isoformat(),
            },
            idempotency_key=f"interview_reminder:{session_id}",
            run_after=reminder_at,
        )


async def send_interview_reminder_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
    session_id: str,
    session_type: str,
    scheduled_at: datetime,
) -> dict[str, Any]:
    """24h-before reminder (background job)."""
    row = await db.fetchrow(
        """
        SELECT vs.status, u.email, u.full_name
        FROM public.voice_sessions vs
        JOIN public.candidates c ON c.id = vs.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE vs.id = $1::uuid AND u.id = $2::uuid
        """,
        uuid.UUID(session_id),
        uuid.UUID(user_id),
    )
    if not row or row["status"] != "scheduled" or not row["email"]:
        return {"sent": False, "skipped": "not_scheduled"}

    dedupe_key = f"reminder:{session_id}"
    if await _already_notified(
        db, user_id=user_id, notif_type="interview_reminder", dedupe_key=dedupe_key, within_hours=48
    ):
        return {"sent": False, "skipped": "deduped"}

    label = session_type.replace("_", " ").title()
    when = scheduled_at.astimezone(UTC).strftime("%a %d %b %Y, %H:%M UTC")
    app_base = _app_base(settings)
    result = await send_category_email(
        db,
        settings,
        user_id=user_id,
        category="interview_reminders",
        to_email=row["email"],
        to_name=row["full_name"],
        template_data={
            "full_name": row["full_name"] or "there",
            "session_label": label,
            "scheduled_label": when,
            "is_reminder": True,
            "cta_url": f"{app_base}/dashboard",
        },
        template_id=settings.sg_template_interview_reminder,
    )
    if result.get("sent"):
        await _log_in_app(
            db,
            user_id=user_id,
            notif_type="interview_reminder",
            title=f"Reminder: {label} tomorrow",
            body=f"Your session is at {when}",
            data={"session_id": session_id, "dedupe_key": dedupe_key},
            channels=["in_app", "email"],
        )
    return result


async def notify_profile_viewed(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    candidate_user_id: str,
    slug: str,
) -> None:
    """Email when a recruiter views a published public profile (max 1/day per slug)."""
    dedupe_key = f"view:{slug}:{datetime.now(UTC).date().isoformat()}"
    if await _already_notified(
        db,
        user_id=candidate_user_id,
        notif_type="profile_view",
        dedupe_key=dedupe_key,
        within_hours=24,
    ):
        return

    user = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(candidate_user_id),
    )
    if not user or not user["email"]:
        return

    app_base = _app_base(settings)
    channels = ["in_app"]
    result = await send_category_email(
        db,
        settings,
        user_id=candidate_user_id,
        category="profile_views",
        to_email=user["email"],
        to_name=user["full_name"],
        template_data={
            "full_name": user["full_name"] or "there",
            "viewer_label": "A recruiter",
            "cta_url": f"{app_base}/dashboard?panel=profile",
        },
    )
    if result.get("sent"):
        channels.append("email")

    await _log_in_app(
        db,
        user_id=candidate_user_id,
        notif_type="profile_view",
        title="Profile viewed",
        body="A recruiter viewed your public profile",
        data={"slug": slug, "dedupe_key": dedupe_key},
        channels=channels,
    )


async def notify_application_update(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    candidate_user_id: str,
    job_id: str,
    job_title: str,
    company_name: str | None,
    status: str,
) -> None:
    """Email when an application is recorded or status changes."""
    dedupe_key = f"app:{job_id}:{status}"
    if await _already_notified(
        db,
        user_id=candidate_user_id,
        notif_type="application_update",
        dedupe_key=dedupe_key,
        within_hours=24,
    ):
        return

    user = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(candidate_user_id),
    )
    if not user or not user["email"]:
        return

    status_label = status.replace("_", " ").title()
    app_base = _app_base(settings)
    channels = ["in_app"]
    result = await send_category_email(
        db,
        settings,
        user_id=candidate_user_id,
        category="application_updates",
        to_email=user["email"],
        to_name=user["full_name"],
        template_data={
            "full_name": user["full_name"] or "there",
            "job_title": job_title,
            "company_name": company_name or "a company",
            "status": status,
            "status_label": status_label,
            "cta_url": f"{app_base}/dashboard?panel=jobs",
        },
    )
    if result.get("sent"):
        channels.append("email")

    await _log_in_app(
        db,
        user_id=candidate_user_id,
        notif_type="application_update",
        title="Application update",
        body=f"{job_title}: {status_label}",
        data={"job_id": job_id, "status": status, "dedupe_key": dedupe_key},
        channels=channels,
    )


async def send_weekly_digest(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
) -> dict[str, Any]:
    """Weekly Aarya digest email (background job)."""
    user = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not user or not user["email"]:
        return {"sent": False, "skipped": "no_email"}

    week_key = datetime.now(UTC).strftime("%G-W%V")
    dedupe_key = f"digest:{week_key}"
    if await _already_notified(
        db,
        user_id=user_id,
        notif_type="aarya_digest",
        dedupe_key=dedupe_key,
        within_hours=24 * 8,
    ):
        return {"sent": False, "skipped": "deduped"}

    stats = await db.fetchrow(
        """
        SELECT
          (SELECT count(*)::int FROM public.notifications n
           WHERE n.user_id = $1::uuid AND n.type = 'job_match'
             AND n.created_at > NOW() - INTERVAL '7 days') AS match_count,
          (SELECT count(*)::int FROM public.notifications n
           WHERE n.user_id = $1::uuid AND n.type = 'intro_status'
             AND n.created_at > NOW() - INTERVAL '7 days') AS intro_count,
          (SELECT count(*)::int FROM public.agent_actions aa
           WHERE aa.user_id = $1::uuid
             AND aa.created_at > NOW() - INTERVAL '7 days') AS actions_count
        """,
        uuid.UUID(user_id),
    )
    match_count = int(stats["match_count"] or 0) if stats else 0
    intro_count = int(stats["intro_count"] or 0) if stats else 0
    actions_count = int(stats["actions_count"] or 0) if stats else 0

    app_base = _app_base(settings)
    result = await send_category_email(
        db,
        settings,
        user_id=user_id,
        category="aarya_digest",
        to_email=user["email"],
        to_name=user["full_name"],
        template_data={
            "full_name": user["full_name"] or "there",
            "match_count": match_count,
            "intro_count": intro_count,
            "actions_count": actions_count,
            "cta_url": f"{app_base}/dashboard",
        },
    )
    if result.get("sent"):
        await _log_in_app(
            db,
            user_id=user_id,
            notif_type="aarya_digest",
            title="Your weekly digest",
            body=f"{match_count} matches · {actions_count} actions",
            data={"dedupe_key": dedupe_key, "week": week_key},
            channels=["in_app", "email"],
        )
    return result


async def schedule_weekly_digest(
    db: asyncpg.Connection,
    *,
    user_id: str,
    first_run_days: int = 7,
) -> None:
    """Enqueue the next weekly digest for a user."""
    from hireloop_api.services.background_jobs import AARYA_WEEKLY_DIGEST, enqueue_job

    run_after = datetime.now(UTC) + timedelta(days=first_run_days)
    week_bucket = run_after.strftime("%G-W%V")
    await enqueue_job(
        db,
        kind=AARYA_WEEKLY_DIGEST,
        payload={"user_id": user_id},
        idempotency_key=f"weekly_digest:{user_id}:{week_bucket}",
        run_after=run_after,
    )
