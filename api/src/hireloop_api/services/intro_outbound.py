"""
Candidate-approved outbound drafts for intros (follow-ups + thank-yous).

All HM-facing mail still goes via the candidate's Gmail OAuth (R9).
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()


def followup_draft_bodies(
    hm_name: str, job_title: str, candidate_name: str
) -> dict[str, str]:
    hm_first = (hm_name or "there").split(" ")[0]
    text = (
        f"Hi {hm_first},\n\n"
        f"Just floating this back to the top of your inbox — I'm still very "
        f"interested in the {job_title or 'the role'} role and would love a "
        f"quick chat if it's still open.\n\n"
        f"Thanks!\n{candidate_name or ''}"
    ).strip()
    html = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
    return {"subject": "", "body_html": html, "body_text": text}


def thankyou_draft_bodies(
    hm_name: str, job_title: str, candidate_name: str, company_name: str | None
) -> dict[str, str]:
    hm_first = (hm_name or "there").split(" ")[0]
    role = job_title or "the role"
    company = company_name or "your team"
    text = (
        f"Hi {hm_first},\n\n"
        f"Thank you for taking the time to connect about the {role} role at "
        f"{company}. I really enjoyed our conversation and remain very "
        f"interested in the opportunity.\n\n"
        f"Happy to share anything else that would be helpful.\n\n"
        f"Best regards,\n{candidate_name or ''}"
    ).strip()
    html = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
    subject = f"Thank you — {role}"
    return {"subject": subject, "body_html": html, "body_text": text}


def _parse_draft(raw: Any) -> dict[str, str] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return {
            "subject": str(raw.get("subject") or ""),
            "body_html": str(raw.get("body_html") or ""),
            "body_text": str(raw.get("body_text") or ""),
        }
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return _parse_draft(data)
    return None


async def ensure_thankyou_draft(
    db: asyncpg.Connection,
    *,
    intro_id: str,
    settings: Any | None = None,
    notify: bool = True,
) -> bool:
    """Create a thank-you draft once if none exists / not sent. Returns True if created."""
    row = await db.fetchrow(
        """
        SELECT ir.id, ir.candidate_id, ir.thankyou_draft_at, ir.thankyou_sent_at,
               ir.gmail_subject, ir.gmail_thread_id,
               j.title AS job_title, co.name AS company_name,
               hm.full_name AS hm_name,
               u.id AS user_id, u.full_name AS candidate_name
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE ir.id = $1::uuid
        """,
        intro_id,
    )
    if not row:
        return False
    if row["thankyou_sent_at"] is not None or row["thankyou_draft_at"] is not None:
        return False

    draft = thankyou_draft_bodies(
        row["hm_name"] or "",
        row["job_title"] or "",
        row["candidate_name"] or "",
        row["company_name"],
    )
    await db.execute(
        """
        UPDATE public.intro_requests
        SET thankyou_draft_email = $2::text,
            thankyou_draft_at = NOW(),
            updated_at = NOW()
        WHERE id = $1::uuid
          AND thankyou_draft_at IS NULL
          AND thankyou_sent_at IS NULL
        """,
        intro_id,
        json.dumps(draft),
    )

    if notify and settings is not None:
        from hireloop_api.services.notifications import _already_notified, _app_base, _log_in_app

        user_id = str(row["user_id"])
        dedupe_key = f"thankyou_draft:{intro_id}"
        if not await _already_notified(
            db, user_id=user_id, notif_type="thankyou_draft", dedupe_key=dedupe_key, within_hours=720
        ):
            title = row["job_title"] or "your role"
            cta = f"{_app_base(settings)}/dashboard?panel=inbox"
            await _log_in_app(
                db,
                user_id=user_id,
                notif_type="thankyou_draft",
                title="Thank-you draft ready",
                body=f"Want to send a short thank-you for **{title}**? Review and approve from your intros.",
                data={"intro_id": intro_id, "dedupe_key": dedupe_key, "deep_link": cta},
                channels=["in_app"],
            )
    return True


async def create_followup_draft_row(
    db: asyncpg.Connection,
    row: asyncpg.Record,
    *,
    settings: Any | None = None,
) -> bool:
    """Persist follow-up draft + notify. Returns True if draft written."""
    subject = row["gmail_subject"] or f"Re: {row['job_title'] or 'the role'}"
    bodies = followup_draft_bodies(
        row["hm_name"] or "",
        row["job_title"] or "",
        row["candidate_name"] or "",
    )
    bodies["subject"] = subject
    result = await db.execute(
        """
        UPDATE public.intro_requests
        SET followup_draft_email = $2::text,
            followup_draft_at = NOW(),
            updated_at = NOW()
        WHERE id = $1::uuid
          AND followup_draft_at IS NULL
          AND nudged_at IS NULL
          AND status = 'sent'
          AND replied_at IS NULL
        """,
        row["id"],
        json.dumps(bodies),
    )
    if result == "UPDATE 0":
        return False

    if settings is not None:
        from hireloop_api.services.notifications import _already_notified, _app_base, _log_in_app

        user_id = str(row["user_id"])
        intro_id = str(row["id"])
        dedupe_key = f"followup_draft:{intro_id}"
        if not await _already_notified(
            db, user_id=user_id, notif_type="followup_draft", dedupe_key=dedupe_key, within_hours=168
        ):
            title = row["job_title"] or "your role"
            company = row["company_name"] or "the company"
            cta = f"{_app_base(settings)}/dashboard?panel=inbox"
            await _log_in_app(
                db,
                user_id=user_id,
                notif_type="followup_draft",
                title="Follow-up ready to approve",
                body=(
                    f"No reply yet on **{title}** at {company}. "
                    "Review the bump and send from your Gmail when you're ready."
                ),
                data={"intro_id": intro_id, "dedupe_key": dedupe_key, "deep_link": cta},
                channels=["in_app"],
            )
    return True


__all__ = [
    "_parse_draft",
    "create_followup_draft_row",
    "ensure_thankyou_draft",
    "followup_draft_bodies",
    "thankyou_draft_bodies",
]
