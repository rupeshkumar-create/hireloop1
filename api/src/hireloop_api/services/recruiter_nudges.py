"""
Recruiter pipeline nudges — stuck candidates, pending intros, stale roles.
"""

from __future__ import annotations

from typing import Any

import asyncpg


async def compute_recruiter_nudges(
    db: asyncpg.Connection,
    *,
    recruiter_id: str,
    role_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return actionable nudges for recruiter dashboard or role workspace."""
    nudges: list[dict[str, Any]] = []

    # Pending candidate→recruiter intros
    intro_row = await db.fetchrow(
        """
        SELECT count(*)::int AS n
        FROM public.intro_requests ir
        WHERE ir.recruiter_id = $1::uuid
          AND ir.direction = 'candidate_to_recruiter'
          AND ir.status = 'pending'
        """,
        recruiter_id,
    )
    if intro_row and intro_row["n"] > 0:
        nudges.append(
            {
                "type": "pending_intros",
                "severity": "high",
                "count": intro_row["n"],
                "message": f"{intro_row['n']} candidate intro request(s) waiting for your response",
                "action": "Open inbox",
                "href": "/recruiter/inbox",
            }
        )

    role_filter = "AND p.role_id = $2::uuid" if role_id else ""
    params: list[Any] = [recruiter_id]
    if role_id:
        params.append(role_id)

    # Stuck in interview stage > 7 days
    stuck = await db.fetchval(
        f"""
        SELECT count(*)::int
        FROM public.role_pipeline p
        JOIN public.roles r ON r.id = p.role_id
        WHERE r.recruiter_id = $1::uuid
          AND r.deleted_at IS NULL
          AND p.stage = 'interview'
          AND p.moved_at < NOW() - INTERVAL '7 days'
          {role_filter}
        """,
        *params,
    )
    if stuck and stuck > 0:
        nudges.append(
            {
                "type": "stuck_interview",
                "severity": "medium",
                "count": stuck,
                "message": f"{stuck} candidate(s) in Interview for over 7 days",
                "action": "Review pipeline",
                "href": f"/recruiter/roles/{role_id}/pipeline" if role_id else "/recruiter/roles",
            }
        )

    # Inbound applicants not reviewed (still in search stage)
    inbound_params: list[Any] = [recruiter_id]
    inbound_filter = ""
    if role_id:
        inbound_filter = "AND ia.role_id = $2::uuid"
        inbound_params.append(role_id)

    inbound_unreviewed = await db.fetchval(
        f"""
        SELECT count(*)::int
        FROM public.role_inbound_applicants ia
        JOIN public.roles r ON r.id = ia.role_id
        WHERE r.recruiter_id = $1::uuid
          AND r.deleted_at IS NULL
          AND ia.stage = 'search'
          AND ia.created_at > NOW() - INTERVAL '14 days'
          {inbound_filter}
        """,
        *inbound_params,
    )
    if inbound_unreviewed and inbound_unreviewed > 0:
        nudges.append(
            {
                "type": "inbound_unreviewed",
                "severity": "medium",
                "count": inbound_unreviewed,
                "message": f"{inbound_unreviewed} inbound applicant(s) to triage",
                "action": "Review pipeline",
                "href": f"/recruiter/roles/{role_id}/pipeline" if role_id else "/recruiter/roles",
            }
        )

    # Roles missing comp
    missing_comp = await db.fetchval(
        """
        SELECT count(*)::int FROM public.roles
        WHERE recruiter_id = $1::uuid AND deleted_at IS NULL
          AND status IN ('draft', 'hiring')
          AND comp_min IS NULL AND comp_max IS NULL
        """,
        recruiter_id,
    )
    if missing_comp and missing_comp > 0 and not role_id:
        nudges.append(
            {
                "type": "missing_comp",
                "severity": "low",
                "count": missing_comp,
                "message": f"{missing_comp} role(s) missing salary band — may get fewer applicants",
                "action": "Add comp in brief",
                "href": "/recruiter/roles",
            }
        )

    return nudges
