"""
Lightweight in-process rate limiter (fixed-window, per client IP).

A first line of defence against abuse / runaway clients on the API, on top of
the per-phone OTP limit and Cloudflare WAF. Deliberately dependency-free and
in-memory: it is PER-PROCESS, so behind multiple workers/instances the effective
limit is Nx the configured value — fine as a safety cap, not a billing-grade
quota. Swap the store for Redis if you need a cluster-wide limit.

Limits are generous so legitimate use is never blocked; they only catch floods.

Important: forwarded IP headers are attacker-controlled unless the immediate
socket peer is a known reverse proxy. They are ignored by default and consulted
only when TRUSTED_PROXY_CIDRS explicitly identifies the deployment's proxies.
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from hireloop_api.config import get_settings

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


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip())
    except ValueError:
        return None


def _client_ip(request: Request, trusted_proxy_cidrs: list[str] | None = None) -> str:
    """Return the direct peer, or the rightmost untrusted XFF hop."""
    peer_host = request.client.host if request.client and request.client.host else ""
    peer = _parse_ip(peer_host)
    if peer is None:
        return peer_host or "unknown"

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in trusted_proxy_cidrs or []:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue

    def is_trusted(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return any(
            address.version == network.version and address in network for network in networks
        )

    if not networks or not is_trusted(peer):
        return str(peer)

    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [address for part in forwarded.split(",") if (address := _parse_ip(part)) is not None]
    for address in reversed(chain):
        if not is_trusted(address):
            return str(address)
    return str(peer)


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

    allowed, retry_after = check_rate_limit(
        _client_ip(request, get_settings().trusted_proxy_cidrs), path
    )
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
