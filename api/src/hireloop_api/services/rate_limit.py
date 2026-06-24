"""
Per-user rate limiting for LLM-spending endpoints (backend plan #48).

Sliding-window counter, in-process. Protects against runaway cost and abuse
(every chat turn / generation is real OpenRouter spend). Scope note: state is
per-process — good for the current single-instance deploy; swap the store for
Postgres/Redis when the API scales horizontally (interface stays the same).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

_WINDOW_SECONDS = 3600

# (user_id, bucket) → deque of event timestamps inside the window.
_events: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def check_rate_limit(
    user_id: str,
    bucket: str,
    max_per_hour: int,
    *,
    now: float | None = None,
) -> None:
    """
    Record one event and raise 429 when the caller exceeds `max_per_hour`
    in a sliding 1-hour window. Cheap: O(evictions) per call.
    """
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


def reset_rate_limits() -> None:
    """Test helper — clear all counters."""
    _events.clear()
