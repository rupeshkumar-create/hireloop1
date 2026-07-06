"""
Intro follow-up sweep — the 72-hour nudge that closes the intro loop.

An intro email that gets no reply usually just fell to the bottom of an
inbox. One polite bump in the SAME Gmail thread (sent from the candidate's
own account, R9) roughly doubles reply rates. At most one nudge per intro
(nudged_at), and only while the intro is still 'sent' with no reply.

Runs from the background worker every ~15 minutes; each pass is capped so
a backlog can never monopolise the worker.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()

NUDGE_AFTER_HOURS = 72
MAX_NUDGES_PER_SWEEP = 10

_NUDGE_TEXT = (
    "Hi {hm_first},\n\n"
    "Just floating this back to the top of your inbox — I'm still very "
    "interested in the {job_title} role and would love a quick chat if it's "
    "still open.\n\n"
    "Thanks!\n{candidate_name}"
)


def _nudge_bodies(hm_name: str, job_title: str, candidate_name: str) -> tuple[str, str]:
    hm_first = (hm_name or "there").split(" ")[0]
    text = _NUDGE_TEXT.format(
        hm_first=hm_first,
        job_title=job_title or "the role",
        candidate_name=candidate_name or "",
    ).strip()
    html = "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
    return html, text


async def run_intro_followup_sweep(db: asyncpg.Connection, settings: Any) -> int:
    """Send one bump per overdue intro. Returns how many nudges were sent."""
    if not (settings.google_client_id and settings.google_client_secret):
        return 0

    rows = await db.fetch(
        f"""
        SELECT ir.id, ir.candidate_id, ir.gmail_thread_id, ir.gmail_subject,
               j.title AS job_title,
               hm.full_name AS hm_name, hm.email AS hm_email,
               u.full_name AS candidate_name
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE ir.status = 'sent'
          AND ir.replied_at IS NULL
          AND ir.nudged_at IS NULL
          AND ir.sent_at < NOW() - INTERVAL '{NUDGE_AFTER_HOURS} hours'
          AND ir.gmail_thread_id IS NOT NULL
          AND hm.email IS NOT NULL
        ORDER BY ir.sent_at ASC
        LIMIT {MAX_NUDGES_PER_SWEEP}
        """
    )
    if not rows:
        return 0

    from hireloop_api.services.email.gmail_oauth import GmailOAuthService

    svc = GmailOAuthService(
        google_client_id=settings.google_client_id,
        google_client_secret=settings.google_client_secret,
        db=db,
    )
    nudged = 0
    try:
        for r in rows:
            html, text = _nudge_bodies(r["hm_name"], r["job_title"], r["candidate_name"])
            # Same subject + threadId keeps Gmail threading intact.
            subject = r["gmail_subject"] or f"Re: {r['job_title']}"
            ok, _info = await svc.send_intro_email(
                candidate_id=str(r["candidate_id"]),
                to_email=r["hm_email"],
                to_name=r["hm_name"] or "",
                subject=subject,
                body_html=html,
                body_text=text,
                thread_id=r["gmail_thread_id"],
            )
            # Mark nudged even on failure (e.g. revoked Gmail token) — retrying
            # a dead token every sweep would spam logs forever; the candidate
            # still sees the intro as sent and can follow up manually.
            await db.execute(
                "UPDATE public.intro_requests SET nudged_at = NOW(), updated_at = NOW() "
                "WHERE id = $1",
                r["id"],
            )
            if ok:
                nudged += 1
                logger.info("intro_nudged", intro_id=str(r["id"]))
            else:
                logger.warning("intro_nudge_failed", intro_id=str(r["id"]))
    finally:
        await svc.close()
    return nudged
