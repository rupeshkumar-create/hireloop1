"""
Notification orchestration — in-app + WhatsApp (MSG91) + email (SendGrid).

Triggers:
  - New high-quality job match (P19)
  - Intro status updates (future)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.whatsapp.msg91 import Msg91Client, resolve_msg91_template_name

logger = structlog.get_logger()

MATCH_NOTIFY_MIN_SCORE = 0.65
JOB_MATCH_TEMPLATE = "job_match_alert"


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
    """Send a SendGrid dynamic template when user prefs + config allow."""
    if not settings.sendgrid_api_key or not template_id:
        return {"sent": False, "skipped": "sendgrid_unconfigured"}

    user = await db.fetchrow(
        "SELECT notification_prefs FROM public.users WHERE id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not user:
        return {"sent": False, "error": "User not found"}

    prefs = user["notification_prefs"] or {}
    cat_prefs = prefs.get(purpose, {}) or prefs.get("intro_updates", {})
    if isinstance(cat_prefs, dict) and cat_prefs.get("email") is False:
        return {"sent": False, "skipped": "opted_out"}

    from hireloop_api.services.email.sendgrid_service import SendGridService

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
            dynamic_data=dynamic_data,
        )
    finally:
        await svc.close()

    return {"sent": sent}


async def notify_intro_status_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    intro_id: str,
    status: str,
) -> dict[str, Any]:
    """Emailing candidate when their intro status changes (transactional — R9)."""
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

    app_base = (
        settings.allowed_origins[0] if settings.allowed_origins else "https://app.hireloop.in"
    )
    if "localhost" in app_base and len(settings.allowed_origins) > 1:
        app_base = next((o for o in settings.allowed_origins if "3001" in o), app_base)

    return await send_email_if_allowed(
        db,
        settings,
        user_id=str(row["user_id"]),
        purpose="intro_updates",
        to_email=row["email"],
        to_name=row["full_name"],
        template_id=settings.sg_template_intro_status,
        dynamic_data={
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
    cat_prefs = prefs.get(purpose, {})
    if purpose.startswith("intro"):
        cat_prefs = cat_prefs or prefs.get("intro_updates", {}) or prefs.get("intro_status", {})
    if isinstance(cat_prefs, dict) and cat_prefs.get("whatsapp") is False:
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
        purpose=purpose,
        payload={"body_params": body_params},
        result=result,
    )
    return result


async def _already_notified_job_match(
    db: asyncpg.Connection,
    user_id: str,
    job_id: str,
) -> bool:
    row = await db.fetchrow(
        """
        SELECT 1 FROM public.notifications
        WHERE user_id = $1::uuid
          AND type = 'job_match'
          AND data->>'job_id' = $2
          AND created_at > NOW() - INTERVAL '24 hours'
        LIMIT 1
        """,
        uuid.UUID(user_id),
        job_id,
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
    """
    Fire in-app + email (SendGrid) + WhatsApp when a strong new match is computed.
    Deduped per user/job per 24h.
    """
    if overall_score < MATCH_NOTIFY_MIN_SCORE:
        return

    row = await db.fetchrow(
        """
        SELECT c.user_id, u.full_name, u.email, u.notification_prefs
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    if not row:
        return

    user_id = str(row["user_id"])
    if await _already_notified_job_match(db, user_id, job_id):
        return

    app_base = (
        settings.allowed_origins[0] if settings.allowed_origins else "https://app.hireloop.in"
    )
    if "localhost" in app_base and len(settings.allowed_origins) > 1:
        app_base = next((o for o in settings.allowed_origins if "3001" in o), app_base)
    deep_link = f"{app_base}/dashboard?job={job_id}"
    pct = str(round(overall_score * 100))
    title = job_title
    company = company_name or "a company"

    notif_body = f"{title} at {company} — {pct}% match"
    data = {"job_id": job_id, "deep_link": deep_link, "score": overall_score}

    channels = ["in_app"]
    if row["email"]:
        email_result = await send_email_if_allowed(
            db,
            settings,
            user_id=user_id,
            purpose="job_match",
            to_email=row["email"],
            to_name=row["full_name"],
            template_id=settings.sg_template_job_match_alert,
            dynamic_data={
                "full_name": row["full_name"] or "there",
                "match_count": 1,
                "top_job_title": title,
                "top_company": company,
                "top_score_pct": int(pct),
                "cta_url": deep_link,
            },
        )
        if email_result.get("sent"):
            channels.append("email")

    wa_result = await send_whatsapp_if_allowed(
        db,
        settings,
        user_id=user_id,
        template_name=JOB_MATCH_TEMPLATE,
        purpose="job_match",
        body_params=[row["full_name"] or "there", title, company, pct, deep_link],
    )
    if wa_result.get("sent"):
        channels.append("whatsapp")

    await db.execute(
        """
        INSERT INTO public.notifications (user_id, type, title, body, data, channels, sent_at)
        VALUES ($1::uuid, 'job_match', $2, $3, $4::jsonb, $5::text[], NOW())
        """,
        uuid.UUID(user_id),
        "New job match",
        notif_body,
        json.dumps(data),
        channels,
    )

    logger.info(
        "job_match_notified",
        user_id=user_id,
        job_id=job_id,
        score=overall_score,
        channels=channels,
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
    await db.execute(
        """
        INSERT INTO public.notifications (user_id, type, title, body, data, channels, sent_at)
        VALUES ($1::uuid, 'intro_status', $2, $3, $4::jsonb, $5::text[], NOW())
        """,
        uuid.UUID(recipient_user_id),
        title,
        body,
        json.dumps({"intro_id": intro_id, "event": event}),
        channels,
    )

    user = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(recipient_user_id),
    )
    if user and user["email"] and email_template_data and settings.sg_template_intro_status:
        email_result = await send_email_if_allowed(
            db,
            settings,
            user_id=recipient_user_id,
            purpose="intro_updates",
            to_email=user["email"],
            to_name=user["full_name"],
            template_id=settings.sg_template_intro_status,
            dynamic_data=email_template_data,
        )
        if email_result.get("sent"):
            channels.append("email")

    if settings.msg91_intro_status_template:
        wa_result = await send_whatsapp_if_allowed(
            db,
            settings,
            user_id=recipient_user_id,
            template_name="intro_status",
            purpose="intro_status",
            body_params=[title, body[:120]],
        )
        if wa_result.get("sent"):
            channels.append("whatsapp")
