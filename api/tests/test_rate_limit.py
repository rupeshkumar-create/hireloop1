"""In-process rate limiter (fixed-window, per IP)."""

from __future__ import annotations

from types import SimpleNamespace

import hireloop_api.rate_limit as rl


def setup_function() -> None:
    rl._buckets.clear()


def test_allows_under_limit_then_blocks_over() -> None:
    t = 1_000_000.0  # fixed window
    for _ in range(rl._DEFAULT_MAX):
        allowed, _ = rl.check_rate_limit("1.2.3.4", "/api/v1/matches/feed", now=t)
        assert allowed
    allowed, retry = rl.check_rate_limit("1.2.3.4", "/api/v1/matches/feed", now=t)
    assert allowed is False
    assert 0 < retry <= rl._WINDOW_SECONDS


def test_sensitive_paths_have_tighter_limit() -> None:
    t = 2_000_000.0
    for _ in range(rl._SENSITIVE_MAX):
        assert rl.check_rate_limit("9.9.9.9", "/api/v1/auth/otp", now=t)[0]
    assert rl.check_rate_limit("9.9.9.9", "/api/v1/auth/otp", now=t)[0] is False


def test_general_traffic_does_not_exhaust_auth_bucket() -> None:
    t = 2_500_000.0
    for _ in range(rl._DEFAULT_MAX):
        assert rl.check_rate_limit("8.8.8.8", "/api/v1/matches/feed", now=t)[0]
    # Auth uses a separate tier counter — still has headroom.
    assert rl.check_rate_limit("8.8.8.8", "/api/v1/auth/me", now=t)[0] is True


def test_window_resets_and_ips_isolated() -> None:
    t = 3_000_000.0
    for _ in range(rl._DEFAULT_MAX):
        rl.check_rate_limit("5.5.5.5", "/api/v1/x", now=t)
    assert rl.check_rate_limit("5.5.5.5", "/api/v1/x", now=t)[0] is False
    assert rl.check_rate_limit("6.6.6.6", "/api/v1/x", now=t)[0] is True
    assert rl.check_rate_limit("5.5.5.5", "/api/v1/x", now=t + rl._WINDOW_SECONDS)[0] is True


def test_client_ip_prefers_cloudflare_and_xff() -> None:
    req = SimpleNamespace(
        headers={
            "cf-connecting-ip": "203.0.113.10",
            "x-forwarded-for": "198.51.100.7, 10.0.0.1",
        },
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert rl._client_ip(req) == "203.0.113.10"  # type: ignore[arg-type]

    req2 = SimpleNamespace(
        headers={"x-forwarded-for": "198.51.100.9, 10.0.0.1"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert rl._client_ip(req2) == "198.51.100.9"  # type: ignore[arg-type]


def test_chat_and_matches_are_exempt_from_ip_middleware() -> None:
    assert rl._is_exempt("/api/v1/health")
    assert rl._is_exempt("/api/v1/chat/sessions/primary")
    assert rl._is_exempt("/api/v1/matches/feed")
    assert rl._is_exempt("/api/v1/application-kits/jobs/abc/prepare")
    assert not rl._is_exempt("/api/v1/auth/me")
