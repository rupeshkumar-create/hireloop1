"""
Lightweight in-process rate limiter (fixed-window, per client IP).

A first line of defence against abuse / runaway clients on the API, on top of
the per-phone OTP limit and Cloudflare WAF. Deliberately dependency-free and
in-memory: it is PER-PROCESS, so behind multiple workers/instances the effective
limit is Nx the configured value — fine as a safety cap, not a billing-grade
quota. Swap the store for Redis if you need a cluster-wide limit.

Limits are generous so legitimate use is never blocked; they only catch floods.

Important: the browser talks to Railway via the Vercel `/hireloop-api` rewrite, so
the socket peer is often a shared Vercel egress IP. We prefer CF-Connecting-IP /
X-Forwarded-For / X-Real-IP for the real client. Counters are also keyed by
path tier so auth and general traffic do not share one bucket against mismatched
limits.
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

_WINDOW_SECONDS = 60
_DEFAULT_MAX = 600  # requests / minute / IP for general endpoints
_SENSITIVE_MAX = 120  # tighter for auth (OTP also has its own per-phone limit)
_SENSITIVE_PREFIXES = ("/api/v1/auth",)
_EXEMPT_PREFIXES = ("/api/v1/health",)
# Authenticated chat / matches fan-out from the dashboard; per-user LLM caps
# in services.rate_limit already protect spend. Skip IP flood control here so a
# shared reverse-proxy IP cannot 429 every Aarya turn.
_EXEMPT_EXACT_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/matches",
    "/api/v1/application-kits",
)

# (ip, tier, window_index) -> count
_buckets: dict[tuple[str, str, int], int] = {}


def _is_public_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _client_ip(request: Request) -> str:
    """Best-effort real client IP behind Cloudflare / Vercel / Railway."""
    candidates: list[str] = []
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        candidates.append(cf.strip())
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        candidates.append(real_ip.strip())
    xff = request.headers.get("x-forwarded-for")
    if xff:
        candidates.extend(part.strip() for part in xff.split(",") if part.strip())
    if request.client and request.client.host:
        candidates.append(request.client.host)

    for host in candidates:
        if _is_public_ip(host):
            return host
    return candidates[0] if candidates else "unknown"


def _tier_for(path: str) -> str:
    if any(path.startswith(p) for p in _SENSITIVE_PREFIXES):
        return "sensitive"
    return "general"


def _limit_for(path: str) -> int:
    if _tier_for(path) == "sensitive":
        return _SENSITIVE_MAX
    return _DEFAULT_MAX


def check_rate_limit(ip: str, path: str, now: float | None = None) -> tuple[bool, int]:
    """Pure-ish core (testable): record a hit and return (allowed, retry_after).

    retry_after is seconds until the current window resets (only meaningful when
    not allowed)."""
    now = time.time() if now is None else now
    window = int(now) // _WINDOW_SECONDS
    tier = _tier_for(path)
    key = (ip, tier, window)
    count = _buckets.get(key, 0) + 1
    _buckets[key] = count

    if len(_buckets) > 10_000:  # opportunistic cleanup of stale windows
        for k in [k for k in _buckets if k[2] < window]:
            _buckets.pop(k, None)

    limit = _limit_for(path)
    if count > limit:
        retry_after = _WINDOW_SECONDS - (int(now) % _WINDOW_SECONDS)
        return False, retry_after
    return True, 0


def _is_exempt(path: str) -> bool:
    if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
        return True
    return any(path.startswith(p) for p in _EXEMPT_EXACT_PREFIXES)


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    path = request.url.path
    if request.method == "OPTIONS" or _is_exempt(path):
        return await call_next(request)

    allowed, retry_after = check_rate_limit(_client_ip(request), path)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "detail": ("Too many requests from this network — wait a moment and try again."),
                "error": {"type": "rate_limited", "message": "Too many requests."},
            },
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)
