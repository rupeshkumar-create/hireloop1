"""
Intro follow-up sweep — approve-first 72h bump drafts.

An intro email that gets no reply usually just fell to the bottom of an
inbox. We prepare a polite bump in the SAME Gmail thread for the candidate
to edit and approve (never auto-send — matches Request Intro trust model).

At most one follow-up draft per intro (`followup_draft_at`); `nudged_at` is
set only after the candidate approves and Gmail send succeeds.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog

from hireloop_api.services.intro_outbound import create_followup_draft_row

logger = structlog.get_logger()

NUDGE_AFTER_HOURS = 72
MAX_NUDGES_PER_SWEEP = 10


async def run_intro_followup_sweep(db: asyncpg.Connection, settings: Any) -> int:
    """Create follow-up drafts for overdue intros. Returns how many drafts created."""
    if not (settings.google_client_id and settings.google_client_secret):
        # Still allow draft creation without Google keys — send happens later.
        pass

    rows = await db.fetch(
        f"""
        SELECT ir.id, ir.candidate_id, ir.gmail_thread_id, ir.gmail_subject,
               j.title AS job_title,
               co.name AS company_name,
               hm.full_name AS hm_name, hm.email AS hm_email,
               u.id AS user_id, u.full_name AS candidate_name
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE ir.status = 'sent'
          AND ir.replied_at IS NULL
          AND ir.nudged_at IS NULL
          AND ir.followup_draft_at IS NULL
          AND ir.sent_at < NOW() - INTERVAL '{NUDGE_AFTER_HOURS} hours'
          AND ir.gmail_thread_id IS NOT NULL
          AND hm.email IS NOT NULL
        ORDER BY ir.sent_at ASC
        LIMIT {MAX_NUDGES_PER_SWEEP}
        """
    )
    if not rows:
        return 0

    drafted = 0
    for r in rows:
        try:
            ok = await create_followup_draft_row(db, r, settings=settings)
            if ok:
                drafted += 1
                logger.info("intro_followup_draft_ready", intro_id=str(r["id"]))
        except Exception as exc:
            logger.warning(
                "intro_followup_draft_failed",
                intro_id=str(r["id"]),
                error=str(exc)[:200],
            )
    return drafted
