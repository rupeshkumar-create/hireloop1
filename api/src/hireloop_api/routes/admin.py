"""
Admin panel API (P23) — compliance, ops, bias audit.
Protected by users.role = 'admin'.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_admin_user, get_db
from hireloop_api.services.linkedin_enrichment import (
    backfill_linkedin_profiles,
    list_pending_linkedin_enrichments,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])


class BiasReviewUpdate(BaseModel):
    reviewed: bool = True
    reviewer_notes: str | None = None


def _shape_observability(
    *,
    action_rows: list,
    funnel_rows: list,
    totals: dict | None,
    window_days: int,
) -> dict:
    """Pure: shape agent-action + intro-funnel aggregates into the admin payload."""
    actions = [
        {
            "action_type": r["action_type"],
            "total": int(r["total"]),
            "avg_ms": int(r["avg_ms"]) if r["avg_ms"] is not None else None,
            "errors": int(r["errors"]),
        }
        for r in action_rows
    ]
    funnel = [{"status": r["status"], "count": int(r["n"])} for r in funnel_rows]
    total_actions = int(totals["actions"]) if totals else 0
    total_errors = int(totals["errors"]) if totals else 0
    error_rate = round(total_errors / total_actions, 4) if total_actions else 0.0
    return {
        "window_days": window_days,
        "totals": {
            "agent_actions": total_actions,
            "errors": total_errors,
            "error_rate": error_rate,
        },
        "agent_actions_by_type": actions,
        "intro_funnel": funnel,
    }


@router.get("/dashboard")
async def admin_dashboard(
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    since = datetime.now(UTC) - timedelta(days=7)
    stats = await db.fetchrow(
        """
        SELECT
          (SELECT count(*) FROM public.users WHERE deleted_at IS NULL) AS total_users,
          (SELECT count(*) FROM public.candidates WHERE deleted_at IS NULL) AS candidates,
          (SELECT count(*) FROM public.recruiters WHERE deleted_at IS NULL) AS recruiters,
          (SELECT count(*) FROM public.jobs WHERE is_active AND country_code = 'IN') AS active_jobs,
          (SELECT count(*) FROM public.intro_requests WHERE created_at > $1) AS intros_7d,
          (SELECT count(*) FROM public.intro_requests
             WHERE status = 'sent' AND created_at > $1) AS intros_sent_7d,
          (SELECT count(*) FROM public.voice_sessions WHERE created_at > $1) AS voice_sessions_7d,
          (SELECT count(*) FROM public.placements) AS placements_total
        """,
        since,
    )
    return dict(stats) if stats else {}


@router.get("/observability")
async def admin_observability(
    window_days: int = Query(default=7, ge=1, le=90),
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Agent-loop observability: action volume, latency, error rate, intro funnel.

    Reads the `agent_actions` table (every Aarya/Nitya tool call) so operators can
    see what the agents are doing, how fast, and how often they error.
    """
    since = datetime.now(UTC) - timedelta(days=window_days)
    action_rows = await db.fetch(
        """
        SELECT action_type,
               count(*) AS total,
               round(avg(duration_ms)) AS avg_ms,
               count(*) FILTER (WHERE result ? 'error') AS errors
        FROM public.agent_actions
        WHERE created_at > $1
        GROUP BY action_type
        ORDER BY total DESC
        """,
        since,
    )
    funnel_rows = await db.fetch(
        """
        SELECT status, count(*) AS n
        FROM public.intro_requests
        WHERE created_at > $1
        GROUP BY status
        ORDER BY n DESC
        """,
        since,
    )
    totals = await db.fetchrow(
        """
        SELECT count(*) AS actions,
               count(*) FILTER (WHERE result ? 'error') AS errors
        FROM public.agent_actions
        WHERE created_at > $1
        """,
        since,
    )
    return _shape_observability(
        action_rows=list(action_rows),
        funnel_rows=list(funnel_rows),
        totals=dict(totals) if totals else None,
        window_days=window_days,
    )


@router.get("/ingestion")
async def admin_ingestion(
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    jobs = await db.fetchrow(
        """
        SELECT
          count(*) FILTER (WHERE is_active) AS active,
          count(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '6 hours') AS refreshed_6h,
          count(DISTINCT apify_job_id) AS unique_apify
        FROM public.jobs WHERE country_code = 'IN'
        """
    )
    embeddings = await db.fetchrow(
        """
        SELECT
          (SELECT count(*) FROM public.job_embeddings) AS jobs_embedded,
          (SELECT count(*) FROM public.candidate_embeddings) AS candidates_embedded
        """
    )
    return {
        "jobs": dict(jobs) if jobs else {},
        "embeddings": dict(embeddings) if embeddings else {},
    }


@router.get("/bias-audit")
async def bias_audit_list(
    limit: int = Query(default=10, ge=1, le=100),
    reviewed: bool | None = None,
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """Sample matches for daily bias review (Warden-style)."""
    if reviewed is None:
        rows = await db.fetch(
            """
            SELECT ma.id, ma.criterion, ma.llm_score, ma.llm_reasoning,
                   ma.bias_flags, ma.reviewed, ma.created_at,
                   ms.overall_score, ms.bias_audit,
                   c.id AS candidate_id, j.title AS job_title
            FROM public.match_audits ma
            LEFT JOIN public.match_scores ms ON ms.id = ma.match_score_id
            LEFT JOIN public.candidates c ON c.id = ma.candidate_id
            LEFT JOIN public.jobs j ON j.id = ms.job_id
            ORDER BY ma.created_at DESC
            LIMIT $1
            """,
            limit,
        )
    else:
        rows = await db.fetch(
            """
            SELECT ma.id, ma.criterion, ma.llm_score, ma.bias_flags, ma.reviewed,
                   ms.overall_score, ms.bias_audit, ms.explanation
            FROM public.match_audits ma
            JOIN public.match_scores ms ON ms.id = ma.match_score_id
            WHERE ma.reviewed = $2
            ORDER BY ma.created_at DESC
            LIMIT $1
            """,
            limit,
            reviewed,
        )

    # Seed from match_scores.bias_audit if audit table empty
    if not rows:
        scores = await db.fetch(
            """
            SELECT id, candidate_id, job_id, overall_score, bias_audit, explanation
            FROM public.match_scores
            WHERE bias_audit != '{}'::jsonb
            ORDER BY computed_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [
            {
                "source": "match_scores",
                "match_score_id": str(s["id"]),
                "overall_score": float(s["overall_score"]),
                "bias_audit": s["bias_audit"],
                "explanation": s["explanation"],
            }
            for s in scores
        ]

    return [dict(r) for r in rows]


@router.patch("/bias-audit/{audit_id}")
async def update_bias_review(
    audit_id: str,
    body: BiasReviewUpdate,
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    result = await db.execute(
        """
        UPDATE public.match_audits SET
          reviewed = $2,
          reviewer_notes = $3
        WHERE id = $1::uuid
        """,
        audit_id,
        body.reviewed,
        body.reviewer_notes,
    )
    if result == "UPDATE 0":
        raise HTTPException(404, "Audit entry not found")
    return {"ok": True}


@router.get("/placements")
async def admin_placements(
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """Manual billing queue until P22 Razorpay (v2)."""
    rows = await db.fetch(
        """
        SELECT p.id, p.status, p.hired_at, p.ctc_inr, p.placement_fee_inr,
               p.admin_notes, r.title AS role_title, u.full_name AS candidate_name
        FROM public.placements p
        LEFT JOIN public.roles r ON r.id = p.role_id
        JOIN public.candidates c ON c.id = p.candidate_id
        JOIN public.users u ON u.id = c.user_id
        ORDER BY p.hired_at DESC
        LIMIT 100
        """
    )
    return [dict(r) for r in rows]


@router.get("/candidates/linkedin-enrichment/pending")
async def admin_pending_linkedin_enrichment(
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """List candidates who have a LinkedIn URL but no Apify profile scrape yet."""
    pending = await list_pending_linkedin_enrichments(db, limit=limit)
    return {"count": len(pending), "candidates": pending}


@router.post("/candidates/linkedin-enrichment/backfill")
async def admin_backfill_linkedin_enrichment(
    limit: int = Query(default=25, ge=1, le=100),
    dry_run: bool = Query(default=False),
    _: dict = Depends(get_admin_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Run Apify LinkedIn profile scraper for candidates missing apify_profile data.
    Processes sequentially with a short delay between runs to protect Apify limits.
    """
    return await backfill_linkedin_profiles(
        db,
        settings,
        limit=limit,
        dry_run=dry_run,
    )


@router.get("/voice/calls")
async def admin_voice_calls(
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT vs.id, vs.session_type, vs.status, vs.scheduled_at,
               vs.duration_secs, u.full_name
        FROM public.voice_sessions vs
        JOIN public.candidates c ON c.id = vs.candidate_id
        JOIN public.users u ON u.id = c.user_id
        ORDER BY vs.created_at DESC
        LIMIT 50
        """
    )
    return [dict(r) for r in rows]


@router.get("/background-jobs")
async def admin_background_jobs(
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
    status: str = Query(default="failed"),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """List recent background jobs — defaults to failed for ops triage."""
    from hireloop_api.services.background_jobs import list_background_jobs

    return await list_background_jobs(db, status=status or None, kind=kind, limit=limit)
