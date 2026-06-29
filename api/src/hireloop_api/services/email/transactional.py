"""
Central SendGrid transactional email triggers (R9).

Signup confirmation, recruiter invites, and HM intro requests are fired here
so auth + intro flows share one deduped code path.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.email.resend_service import ResendService
from hireloop_api.services.email.sendgrid_service import SendGridService
from hireloop_api.services.email.smtp_service import SmtpService

logger = structlog.get_logger()

_SIGNUP_EMAIL_PURPOSE = "signup_confirmation_email"


def _html_email_configured(settings: Settings) -> bool:
    """True when we can send a raw-HTML email (SMTP or Resend)."""
    smtp = bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)
    return smtp or bool(settings.resend_api_key)


async def _send_html_email(
    settings: Settings, *, to_email: str, subject: str, html: str
) -> bool:
    """Send one HTML email via the best configured provider.

    Order: generic SMTP (free, e.g. Gmail — delivers to any recipient) → Resend
    (free tier mails only the account owner). Best-effort; returns False if no
    provider is configured or the send fails.
    """
    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        svc = SmtpService(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            from_email=settings.smtp_from,
            from_name=settings.resend_from_name,
        )
        return await svc.send(to_email=to_email, subject=subject, html=html)
    if settings.resend_api_key:
        svc = ResendService(
            settings.resend_api_key, settings.resend_from_email, settings.resend_from_name
        )
        try:
            return await svc.send(to_email=to_email, subject=subject, html=html)
        finally:
            await svc.close()
    return False


def _email_shell(heading: str, body_html: str, cta_url: str, cta_label: str) -> str:
    """Minimal, client-safe HTML wrapper for Resend emails (inline styles)."""
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1a1a1a">
  <h2 style="font-size:20px;margin:0 0 12px">{heading}</h2>
  {body_html}
  <p style="margin:24px 0">
    <a href="{cta_url}" style="background:#111;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;display:inline-block">{cta_label}</a>
  </p>
  <p style="font-size:12px;color:#888;margin-top:24px">Hireloop — India-first AI recruiting</p>
</div>"""


async def _signup_email_already_sent(db: asyncpg.Connection, user_id: uuid.UUID) -> bool:
    row = await db.fetchrow(
        """
        SELECT 1 FROM public.consent_log
        WHERE user_id = $1 AND purpose = $2
        LIMIT 1
        """,
        user_id,
        _SIGNUP_EMAIL_PURPOSE,
    )
    return row is not None


async def _mark_signup_email_sent(db: asyncpg.Connection, user_id: uuid.UUID) -> None:
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1, $2, TRUE)
        """,
        user_id,
        _SIGNUP_EMAIL_PURPOSE,
    )


async def maybe_send_signup_confirmation(
    db: asyncpg.Connection | None,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    email: str | None = None,
    full_name: str | None = None,
) -> dict[str, Any]:
    """
    Welcome email after phone verification / save-phone (once per user).
    Best-effort — never raises.
    """
    use_html = _html_email_configured(settings)  # SMTP (free, any recipient) or Resend
    use_sendgrid = bool(settings.sendgrid_api_key and settings.sg_template_signup_confirmation)
    if not (use_html or use_sendgrid):
        return {"sent": False, "skipped": "email_unconfigured"}

    if db is not None:
        if await _signup_email_already_sent(db, user_id):
            return {"sent": False, "skipped": "already_sent"}
        if not email or not full_name:
            row = await db.fetchrow(
                """
                SELECT email, full_name
                FROM public.users
                WHERE id = $1 AND deleted_at IS NULL
                """,
                user_id,
            )
            if row:
                email = email or row["email"]
                full_name = full_name or row["full_name"]

    if not email:
        return {"sent": False, "skipped": "no_email"}

    display_name = full_name or "there"
    if use_html:
        sent = await _send_html_email(
            settings,
            to_email=email,
            subject="Welcome to Hireloop",
            html=_email_shell(
                f"Welcome, {display_name} 👋",
                "<p style='font-size:14px;line-height:1.6'>You're in. Tell Aarya what you're "
                "looking for and she'll surface live India roles that fit your profile.</p>",
                f"{settings.public_app_url.rstrip('/')}/dashboard",
                "Open Hireloop",
            ),
        )
    else:
        sg = SendGridService(
            settings.sendgrid_api_key,
            settings.sendgrid_from_email,
            settings.sendgrid_from_name,
        )
        try:
            sent = await sg.send_signup_confirmation(
                to_email=email,
                full_name=display_name,
                template_id=settings.sg_template_signup_confirmation,
            )
        finally:
            await sg.close()

    if sent and db is not None:
        try:
            await _mark_signup_email_sent(db, user_id)
        except Exception as exc:
            logger.error("signup_email_consent_log_failed", user_id=str(user_id), error=str(exc))

    return {"sent": bool(sent)}


async def send_job_match_alert(
    db: asyncpg.Connection,
    settings: Settings,
    candidate_id: str,
    *,
    min_score: float = 0.55,
    limit: int = 3,
    cooldown_hours: int = 20,
) -> dict[str, Any]:
    """Email a candidate a digest of their strongest new matches.

    Best-effort and self-throttling: skips if no email provider is configured,
    the candidate has no email, there are no strong matches, or a job-match email
    went out within `cooldown_hours` (deduped via the notifications table).
    """
    if not _html_email_configured(settings):
        return {"sent": False, "skipped": "email_unconfigured"}

    row = await db.fetchrow(
        """
        SELECT u.id AS user_id, u.email, u.full_name
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(candidate_id),
    )
    if not row or not row["email"]:
        return {"sent": False, "skipped": "no_email"}
    user_id = row["user_id"]

    recent = await db.fetchval(
        """
        SELECT 1 FROM public.notifications
        WHERE user_id = $1 AND type = 'job_match'
          AND created_at > NOW() - make_interval(hours => $2)
        LIMIT 1
        """,
        user_id,
        cooldown_hours,
    )
    if recent:
        return {"sent": False, "skipped": "cooldown"}

    jobs = await db.fetch(
        """
        SELECT j.title, co.name AS company, ms.overall_score
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ms.candidate_id = $1::uuid AND ms.overall_score >= $2
          AND j.is_active = TRUE AND j.deleted_at IS NULL AND j.expires_at > NOW()
        ORDER BY ms.overall_score DESC
        LIMIT $3
        """,
        uuid.UUID(candidate_id),
        min_score,
        limit,
    )
    if not jobs:
        return {"sent": False, "skipped": "no_matches"}

    name = row["full_name"] or "there"
    rows_html = "".join(
        f"<li style='margin:6px 0;font-size:14px'><b>{j['title']}</b>"
        f"{(' · ' + j['company']) if j['company'] else ''} "
        f"<span style='color:#16a34a'>({round(float(j['overall_score']) * 100)}% match)</span></li>"
        for j in jobs
    )
    html = _email_shell(
        f"{len(jobs)} new role{'s' if len(jobs) != 1 else ''} that fit you, {name}",
        f"<ul style='padding-left:18px;margin:0'>{rows_html}</ul>",
        f"{settings.public_app_url.rstrip('/')}/dashboard?panel=jobs",
        "View your matches",
    )

    sent = await _send_html_email(
        settings,
        to_email=row["email"],
        subject=f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} on Hireloop",
        html=html,
    )

    if sent:
        try:
            await db.execute(
                """
                INSERT INTO public.notifications
                  (user_id, type, title, body, channels, sent_at)
                VALUES ($1, 'job_match', $2, $3, ARRAY['email','in_app'], NOW())
                """,
                user_id,
                f"{len(jobs)} new job matches",
                "We found roles that fit your profile — open Hireloop to view them.",
            )
        except Exception as exc:
            logger.error("job_match_notification_log_failed", error=str(exc)[:200])

    return {"sent": bool(sent), "count": len(jobs)}
