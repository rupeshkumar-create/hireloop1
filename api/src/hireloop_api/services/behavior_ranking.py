"""
Behavior-based ranking adjustments from impressions, saves, and dismissals.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()

# Position-aware weights — jobs shown higher get more clicks; discount position bias
POSITION_DISCOUNT = {1: 1.0, 2: 0.95, 3: 0.9, 4: 0.85, 5: 0.8}


async def fetch_job_behavior_signals(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Return per-job behavior multipliers from recent interactions."""
    if not job_ids:
        return {}

    uuids = [uuid.UUID(j) for j in job_ids if j]
    rows = await db.fetch(
        """
        SELECT job_id,
               count(*) FILTER (WHERE event_type = 'impression') AS impressions,
               count(*) FILTER (WHERE event_type = 'open') AS opens,
               count(*) FILTER (WHERE event_type = 'save') AS saves,
               count(*) FILTER (WHERE event_type = 'dismiss') AS dismissals,
               count(*) FILTER (WHERE event_type = 'apply_start') AS apply_starts
        FROM public.candidate_job_impressions
        WHERE candidate_id = $1::uuid
          AND job_id = ANY($2::uuid[])
          AND created_at > NOW() - INTERVAL '90 days'
        GROUP BY job_id
        """,
        candidate_id,
        uuids,
    )

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        jid = str(row["job_id"])
        saves = int(row["saves"] or 0)
        dismissals = int(row["dismissals"] or 0)
        apply_starts = int(row["apply_starts"] or 0)
        opens = int(row["opens"] or 0)

        boost = 1.0
        if saves > 0:
            boost += 0.08 * min(saves, 3)
        if apply_starts > 0:
            boost += 0.12 * min(apply_starts, 2)
        if opens > 2 and saves == 0 and apply_starts == 0:
            boost -= 0.05  # viewed but not engaged
        if dismissals > 0:
            boost -= 0.15 * min(dismissals, 3)

        out[jid] = {
            "behavior_multiplier": max(0.5, min(1.25, boost)),
            "saves": saves,
            "dismissals": dismissals,
            "apply_starts": apply_starts,
        }
    return out


def apply_behavior_multiplier(
    jobs: list[dict[str, Any]],
    signals: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply behavior boost to final retrieval scores."""
    out: list[dict[str, Any]] = []
    for job in jobs:
        item = dict(job)
        jid = str(item.get("job_id") or item.get("id") or "")
        sig = signals.get(jid, {})
        mult = float(sig.get("behavior_multiplier") or 1.0)
        base = float(item.get("_retrieval_score") or item.get("_recall_rank_score") or 0.0)
        if base:
            item["_behavior_adjusted_score"] = round(base * mult, 6)
        else:
            item["_behavior_adjusted_score"] = base
        item["behavior_signals"] = sig
        out.append(item)
    return out
