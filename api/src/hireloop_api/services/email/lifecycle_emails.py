"""
Send lifecycle emails via Resend with consent_log deduplication.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.email.lifecycle_templates import (
    render_first_job_found_email,
    render_intro_requested_candidate_email,
    render_recruiter_approach_candidate_email,
    render_recruiter_intro_request_email,
)
from hireloop_api.services.email.transactional import _html_email_configured, _send_html_email

logger = structlog.get_logger()


def _app_base(settings: Settings) -> str:
    base = settings.public_app_url.rstrip("/") if settings.public_app_url else ""
    if base and "localhost" not in base:
        return base
    if settings.allowed_origins:
        for origin in settings.allowed_origins:
            if "hireschema" in origin:
                return origin.rstrip("/")
    return "https://www.hireschema.com"


async def _already_sent(db: asyncpg.Connection, user_id: uuid.UUID, purpose: str) -> bool:
    row = await db.fetchrow(
        """
        SELECT 1 FROM public.consent_log
        WHERE user_id = $1 AND purpose = $2
        LIMIT 1
        """,
        user_id,
        purpose,
    )
    return row is not None


async def _mark_sent(db: asyncpg.Connection, user_id: uuid.UUID, purpose: str) -> None:
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1, $2, TRUE)
        """,
        user_id,
        purpose,
    )


async def _send_once(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    email: str,
    purpose: str,
    subject: str,
    html: str,
) -> dict[str, Any]:
    if not _html_email_configured(settings):
        return {"sent": False, "skipped": "email_unconfigured"}
    if await _already_sent(db, user_id, purpose):
        return {"sent": False, "skipped": "already_sent"}
    sent = await _send_html_email(settings, to_email=email, subject=subject, html=html)
    if sent:
        try:
            await _mark_sent(db, user_id, purpose)
        except Exception as exc:
            logger.warning(
                "lifecycle_email_consent_log_failed", purpose=purpose, error=str(exc)[:200]
            )
    return {"sent": bool(sent)}


async def send_first_job_found_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    candidate_id: str,
    job_id: str,
    job_title: str,
    company_name: str | None,
    overall_score: float,
) -> dict[str, Any]:
    """One-time celebration email when the candidate gets their first strong match."""
    row = await db.fetchrow(
        """
        SELECT c.user_id, u.email, u.full_name
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(candidate_id),
    )
    if not row or not row["email"]:
        return {"sent": False, "skipped": "no_email"}

    user_id = row["user_id"]
    purpose = "first_job_found_email"
    subject, html = render_first_job_found_email(
        full_name=row["full_name"],
        job_title=job_title,
        company_name=company_name,
        score_pct=round(float(overall_score) * 100),
        app_base_url=_app_base(settings),
        job_id=job_id,
    )
    return await _send_once(
        db,
        settings,
        user_id=user_id,
        email=row["email"],
        purpose=purpose,
        subject=subject,
        html=html,
    )


async def notify_intro_requested_to_candidate(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
    job_title: str,
    company_name: str | None,
) -> dict[str, Any]:
    """Confirm to the candidate that their intro request was received."""
    from hireloop_api.services.notifications import send_category_email

    row = await db.fetchrow(
        "SELECT email, full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not row or not row["email"]:
        return {"sent": False, "skipped": "no_email"}

    subject, html = render_intro_requested_candidate_email(
        full_name=row["full_name"],
        job_title=job_title,
        company_name=company_name,
        app_base_url=_app_base(settings),
    )
    if _html_email_configured(settings):
        sent = await _send_html_email(settings, to_email=row["email"], subject=subject, html=html)
        if sent:
            return {"sent": True}
    return await send_category_email(
        db,
        settings,
        user_id=user_id,
        category="intro_updates",
        to_email=row["email"],
        to_name=row["full_name"],
        template_data={
            "full_name": row["full_name"],
            "status_message": f"We received your intro request for {job_title}.",
            "job_title": job_title,
            "company_name": company_name,
            "cta_url": f"{_app_base(settings)}/dashboard?panel=inbox",
        },
    )


async def send_recruiter_intro_request_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    recruiter_id: uuid.UUID,
    candidate_name: str | None,
    job_title: str | None,
) -> bool:
    """Email a registered recruiter when a candidate requests an intro (Resend HTML)."""
    row = await db.fetchrow(
        """
        SELECT u.email, u.full_name
        FROM public.recruiters r
        JOIN public.users u ON u.id = r.user_id
        WHERE r.id = $1::uuid AND r.deleted_at IS NULL
        """,
        recruiter_id,
    )
    if not row or not row["email"]:
        return False
    if not _html_email_configured(settings):
        logger.info("recruiter_intro_email_skipped", reason="email_unconfigured")
        return False

    subject, html = render_recruiter_intro_request_email(
        recruiter_name=row["full_name"],
        candidate_name=candidate_name or "A candidate",
        job_title=job_title or "your role",
        app_base_url=_app_base(settings),
    )
    return await _send_html_email(
        settings,
        to_email=row["email"],
        subject=subject,
        html=html,
    )


async def notify_recruiter_approach_to_candidate(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    candidate_id: uuid.UUID,
    job_title: str,
    company_name: str | None,
    recruiter_name: str | None,
) -> dict[str, Any]:
    """Email candidate when a recruiter requests an intro to them."""
    row = await db.fetchrow(
        """
        SELECT c.user_id, u.email, u.full_name
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    if not row or not row["email"]:
        return {"sent": False, "skipped": "no_email"}

    subject, html = render_recruiter_approach_candidate_email(
        candidate_name=row["full_name"],
        recruiter_name=recruiter_name,
        job_title=job_title,
        company_name=company_name,
        app_base_url=_app_base(settings),
    )
    if not _html_email_configured(settings):
        return {"sent": False, "skipped": "email_unconfigured"}

    sent = await _send_html_email(
        settings,
        to_email=row["email"],
        subject=subject,
        html=html,
    )
    if sent:
        from hireloop_api.services.notifications import _log_in_app

        await _log_in_app(
            db,
            user_id=str(row["user_id"]),
            notif_type="intro_updates",
            title="A recruiter wants to connect",
            body=f"{recruiter_name or 'A recruiter'} is interested in you for {job_title}.",
            data={"deep_link": f"{_app_base(settings)}/dashboard?panel=inbox"},
            channels=["in_app", "email"],
        )
    return {"sent": bool(sent)}
