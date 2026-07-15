"""
Per-user rate limiting for LLM-spending endpoints (backend plan #48).

Uses Postgres `api_rate_limits` when a DB connection is provided so limits are
cluster-wide across API replicas. Falls back to an in-process sliding window
when `db` is None (unit tests / emergency).
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque

import asyncpg
import structlog
from fastapi import HTTPException, status

from hireloop_api.services.distributed_rate_limit import check_distributed_rate_limit

logger = structlog.get_logger()

_WINDOW_SECONDS = 3600

# (user_id, bucket) → deque of event timestamps inside the window.
_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _user_identity_hash(user_id: str) -> str:
    return hashlib.sha256(f"user:{user_id}".encode()).hexdigest()


def _check_in_memory(
    user_id: str,
    bucket: str,
    max_per_hour: int,
    *,
    now: float | None = None,
) -> None:
    ts = now if now is not None else time.time()
    q = _events[(user_id, bucket)]
    cutoff = ts - _WINDOW_SECONDS
    while q and q[0] <= cutoff:
        q.popleft()
    if len(q) >= max_per_hour:
        retry_in = int(q[0] + _WINDOW_SECONDS - ts) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "You've hit the hourly limit for this action — "
                f"try again in about {max(1, retry_in // 60)} min."
            ),
            headers={"Retry-After": str(retry_in)},
        )
    q.append(ts)


async def check_rate_limit(
    user_id: str,
    bucket: str,
    max_per_hour: int,
    *,
    db: asyncpg.Connection | None = None,
    now: float | None = None,
) -> None:
    """
    Record one event and raise 429 when the caller exceeds `max_per_hour`
    in a 1-hour window. Prefer Postgres when `db` is provided.
    """
    if db is not None:
        try:
            await check_distributed_rate_limit(
                db,
                identity_hash=_user_identity_hash(user_id),
                bucket=bucket,
                max_per_hour=max_per_hour,
            )
            return
        except HTTPException:
            raise
        except Exception as exc:
            # Table missing / DB flaky — degrade to in-memory rather than 500.
            logger.warning(
                "distributed_rate_limit_fallback",
                bucket=bucket,
                error=str(exc)[:200],
            )
    _check_in_memory(user_id, bucket, max_per_hour, now=now)


def reset_rate_limits() -> None:
    """Test helper — clear all in-memory counters."""
    _events.clear()
