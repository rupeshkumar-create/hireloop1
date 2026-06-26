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
from hireloop_api.services.email.sendgrid_service import SendGridService

logger = structlog.get_logger()

_SIGNUP_EMAIL_PURPOSE = "signup_confirmation_email"


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
    if not settings.sendgrid_api_key or not settings.sg_template_signup_confirmation:
        return {"sent": False, "skipped": "sendgrid_unconfigured"}

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
    svc = SendGridService(
        settings.sendgrid_api_key,
        settings.sendgrid_from_email,
        settings.sendgrid_from_name,
    )
    try:
        sent = await svc.send_signup_confirmation(
            to_email=email,
            full_name=display_name,
            template_id=settings.sg_template_signup_confirmation,
        )
    finally:
        await svc.close()

    if sent and db is not None:
        try:
            await _mark_signup_email_sent(db, user_id)
        except Exception as exc:
            logger.error("signup_email_consent_log_failed", user_id=str(user_id), error=str(exc))

    return {"sent": bool(sent)}
