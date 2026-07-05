"""Helpers for 'show me new jobs' — skip roles already surfaced in this chat."""

from __future__ import annotations

import json
from typing import Any

import asyncpg

_FRESH_JOB_PHRASES = (
    "something new",
    "something else",
    "find me new",
    "new jobs",
    "new roles",
    "new matches",
    "more jobs",
    "more roles",
    "more matches",
    "more options",
    "other jobs",
    "other roles",
    "other options",
    "different job",
    "different roles",
    "different matches",
    "show me more",
    "any more",
    "anything else",
    "refresh",
    "search again",
    "not this one",
    "not these",
    "keep looking",
)


def wants_fresh_job_results(message: str) -> bool:
    """True when the candidate is asking for jobs they haven't seen yet."""
    text = (message or "").lower()
    return any(phrase in text for phrase in _FRESH_JOB_PHRASES)


async def fetch_shown_job_ids(
    db: asyncpg.Connection,
    session_id: str,
) -> list[str]:
    """Job IDs already returned by job_search in this conversation."""
    rows = await db.fetch(
        """
        SELECT result FROM public.agent_actions
        WHERE agent = 'aarya'
          AND action_type = 'job_search'
          AND session_id = $1::uuid
        ORDER BY created_at ASC
        """,
        session_id,
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        result = row["result"]
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(result, dict):
            continue
        jobs: list[Any] = result.get("jobs") or []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            job_id = job.get("job_id") or job.get("id")
            if not job_id:
                continue
            jid = str(job_id)
            if jid not in seen:
                seen.add(jid)
                ordered.append(jid)
    return ordered


def compute_job_search_fetch_limit(*, limit: int, exclude_count: int) -> int:
    """Pull extra rows so exclusions still leave enough matches."""
    return min(max(limit + exclude_count * 2, limit * 3), 50)


def exclude_job_rows(
    rows: list[dict[str, Any]],
    *,
    exclude_job_ids: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if not exclude_job_ids:
        return rows[:limit]
    blocked = {str(jid) for jid in exclude_job_ids}
    filtered = [r for r in rows if str(r.get("id")) not in blocked]
    return filtered[:limit]
