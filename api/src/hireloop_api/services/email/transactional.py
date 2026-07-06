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


def _sendgrid_usable(settings: Settings) -> bool:
    """True when SendGrid has a real API key (not a placeholder like SG....)."""
    key = (settings.sendgrid_api_key or "").strip()
    if not key or len(key) < 24:
        return False
    if key in ("SG....", "SG...", "SG.."):
        return False
    return key.startswith("SG.")


def _html_email_configured(settings: Settings) -> bool:
    """True when we can send a raw-HTML email (SMTP or Resend)."""
    smtp = bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)
    return smtp or bool(settings.resend_api_key)


async def _send_html_email(settings: Settings, *, to_email: str, subject: str, html: str) -> bool:
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
  <p style="font-size:12px;color:#888;margin-top:24px">Hireschema — AI recruiting for India, the US &amp; the UK</p>
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
    use_sendgrid = _sendgrid_usable(settings) and bool(settings.sg_template_signup_confirmation)
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
            subject="Welcome to Hireschema",
            html=_email_shell(
                f"Welcome, {display_name} 👋",
                "<p style='font-size:14px;line-height:1.6'>You're in. Tell Aarya what you're "
                "looking for and she'll surface live roles in your market that fit your profile.</p>",
                f"{settings.public_app_url.rstrip('/')}/dashboard",
                "Open Hireschema",
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


async def send_recruiter_invite_email(
    settings: Settings,
    *,
    to_email: str,
    invited_name: str | None,
    candidate_name: str,
    job_title: str,
    cta_url: str,
) -> bool:
    """
    Invite an unregistered hiring manager to view a candidate intro (R9 transactional).

    Prefer Resend/SMTP HTML — same provider as Supabase Auth signup OTP when
    ``RESEND_API_KEY`` + ``RESEND_FROM_EMAIL`` match the Supabase custom SMTP setup.
    SendGrid templates are used only when a real API key and template ID exist.
    """
    template_id = settings.sg_template_recruiter_invite or settings.sg_template_intro_status
    subject = f"{candidate_name} wants an intro — {job_title}"
    body_html = (
        f"<p style='font-size:14px;line-height:1.6'><strong>{candidate_name}</strong> "
        f"requested an intro for <strong>{job_title}</strong> on Hireschema.</p>"
        "<p style='font-size:14px;line-height:1.6'>You're not on Hireschema yet — "
        "accept the invite to view their profile and start a conversation.</p>"
    )
    html = _email_shell(
        f"Hi {invited_name or 'there'}, a candidate wants to connect",
        body_html,
        cta_url,
        "View candidate & accept invite",
    )

    # Same path as signup OTP: Resend (or custom SMTP) from rupesh.kumar@candidate.ly, etc.
    if _html_email_configured(settings):
        sent = await _send_html_email(
            settings,
            to_email=to_email,
            subject=subject,
            html=html,
        )
        if sent:
            return True

    if _sendgrid_usable(settings) and template_id:
        sg = SendGridService(
            settings.sendgrid_api_key,
            settings.sendgrid_from_email,
            settings.sendgrid_from_name,
        )
        try:
            return await sg.send_recruiter_invite(
                to_email=to_email,
                invited_name=invited_name,
                template_id=template_id,
                candidate_name=candidate_name,
                job_title=job_title,
                cta_url=cta_url,
            )
        finally:
            await sg.close()

    if _sendgrid_usable(settings):
        sg = SendGridService(
            settings.sendgrid_api_key,
            settings.sendgrid_from_email,
            settings.sendgrid_from_name,
        )
        try:
            return await sg.send_raw_html(to_email, subject, html)
        finally:
            await sg.close()

    return False


async def send_job_match_alert(
    db: asyncpg.Connection,
    settings: Settings,
    candidate_id: str,
    *,
    min_score: float = 0.55,
    limit: int = 3,
    cooldown_hours: int = 20,
) -> dict[str, Any]:
    """Email a candidate a digest of their strongest new matches (Resend + prefs)."""
    from hireloop_api.services.notifications import send_category_email

    if not settings.resend_api_key and not (
        settings.smtp_host and settings.smtp_user and settings.smtp_password
    ):
        return {"sent": False, "skipped": "email_unconfigured"}

    row = await db.fetchrow(
        """
        SELECT c.user_id, u.id AS uid, u.email, u.full_name, u.notification_prefs
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(candidate_id),
    )
    if not row or not row["email"]:
        return {"sent": False, "skipped": "no_email"}
    user_id = str(row["user_id"])

    recent = await db.fetchval(
        """
        SELECT 1 FROM public.notifications
        WHERE user_id = $1 AND type = 'job_match'
          AND created_at > NOW() - make_interval(hours => $2)
        LIMIT 1
        """,
        row["uid"],
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

    job_payload = [
        {
            "title": j["title"],
            "company": j["company"],
            "score_pct": round(float(j["overall_score"]) * 100),
        }
        for j in jobs
    ]
    app_base = settings.public_app_url.rstrip("/") or "https://www.hireschema.com"

    result = await send_category_email(
        db,
        settings,
        user_id=user_id,
        category="job_match_alerts",
        to_email=row["email"],
        to_name=row["full_name"],
        template_data={
            "full_name": row["full_name"] or "there",
            "jobs": job_payload,
            "cta_url": f"{app_base}/dashboard?panel=jobs",
        },
        template_id=settings.sg_template_job_match_alert,
    )

    if result.get("sent"):
        try:
            await db.execute(
                """
                INSERT INTO public.notifications
                  (user_id, type, title, body, channels, sent_at)
                VALUES ($1, 'job_match', $2, $3, ARRAY['email','in_app'], NOW())
                """,
                row["uid"],
                f"{len(jobs)} new job matches",
                "We found roles that fit your profile — open Hireschema to view them.",
            )
        except Exception as exc:
            logger.error("job_match_notification_log_failed", error=str(exc)[:200])

    return {"sent": bool(result.get("sent")), "count": len(jobs)}
