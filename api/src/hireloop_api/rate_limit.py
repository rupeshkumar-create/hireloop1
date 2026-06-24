"""
Lightweight in-process rate limiter (fixed-window, per client IP).

A first line of defence against abuse / runaway clients on the API, on top of
the per-phone OTP limit and Cloudflare WAF. Deliberately dependency-free and
in-memory: it is PER-PROCESS, so behind multiple workers/instances the effective
limit is Nx the configured value — fine as a safety cap, not a billing-grade
quota. Swap the store for Redis if you need a cluster-wide limit.

Limits are generous so legitimate use is never blocked; they only catch floods.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

_WINDOW_SECONDS = 60
_DEFAULT_MAX = 300  # requests / minute / IP for general endpoints
_SENSITIVE_MAX = 60  # tighter for auth (OTP also has its own per-phone limit)
_SENSITIVE_PREFIXES = ("/api/v1/auth",)
_EXEMPT_PREFIXES = ("/api/v1/health",)

# (ip, window_index) -> count. Pruned opportunistically; bounded in practice by
# (#active IPs) since only the current window is ever incremented.
_buckets: dict[tuple[str, int], int] = {}


def _client_ip(request: Request) -> str:
    """Real client IP: first hop of X-Forwarded-For (set by Cloudflare), else the
    socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_for(path: str) -> int:
    if any(path.startswith(p) for p in _SENSITIVE_PREFIXES):
        return _SENSITIVE_MAX
    return _DEFAULT_MAX


def check_rate_limit(ip: str, path: str, now: float | None = None) -> tuple[bool, int]:
    """Pure-ish core (testable): record a hit and return (allowed, retry_after).

    retry_after is seconds until the current window resets (only meaningful when
    not allowed)."""
    now = time.time() if now is None else now
    window = int(now) // _WINDOW_SECONDS
    key = (ip, window)
    count = _buckets.get(key, 0) + 1
    _buckets[key] = count

    if len(_buckets) > 10_000:  # opportunistic cleanup of stale windows
        for k in [k for k in _buckets if k[1] < window]:
            _buckets.pop(k, None)

    limit = _limit_for(path)
    if count > limit:
        retry_after = _WINDOW_SECONDS - (int(now) % _WINDOW_SECONDS)
        return False, retry_after
    return True, 0


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    path = request.url.path
    if request.method == "OPTIONS" or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return await call_next(request)

    allowed, retry_after = check_rate_limit(_client_ip(request), path)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": {"type": "rate_limited", "message": "Too many requests."}},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
