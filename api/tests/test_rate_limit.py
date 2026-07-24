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


def test_client_ip_ignores_spoofed_forwarding_headers_from_untrusted_peer() -> None:
    req = SimpleNamespace(
        headers={
            "cf-connecting-ip": "1.1.1.1",
            "x-real-ip": "2.2.2.2",
            "x-forwarded-for": "3.3.3.3",
        },
        client=SimpleNamespace(host="8.8.8.8"),
    )
    assert rl._client_ip(req, trusted_proxy_cidrs=["10.0.0.0/8"]) == "8.8.8.8"  # type: ignore[arg-type]


def test_client_ip_uses_rightmost_untrusted_address_in_trusted_proxy_chain() -> None:
    req = SimpleNamespace(
        headers={
            "cf-connecting-ip": "1.1.1.1",
            "x-forwarded-for": "9.9.9.9, 172.16.0.8, 10.0.0.3",
        },
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert (
        rl._client_ip(  # type: ignore[arg-type]
            req,
            trusted_proxy_cidrs=["10.0.0.0/8", "172.16.0.0/12"],
        )
        == "9.9.9.9"
    )


def test_client_ip_ignores_malformed_forwarded_addresses() -> None:
    req = SimpleNamespace(
        headers={"x-forwarded-for": "not-an-ip, 9.9.9.9, also-bad"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert rl._client_ip(req, trusted_proxy_cidrs=["10.0.0.0/8"]) == "9.9.9.9"  # type: ignore[arg-type]


def test_client_ip_defaults_to_direct_peer_without_trusted_proxy_config() -> None:
    req = SimpleNamespace(
        headers={"x-forwarded-for": "9.9.9.9"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert rl._client_ip(req) == "10.0.0.2"  # type: ignore[arg-type]


def test_railway_proxy_headers_are_ignored_unless_explicitly_enabled() -> None:
    req = SimpleNamespace(
        headers={"x-real-ip": "9.9.9.9"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert rl._client_ip(req, trust_railway_proxy_headers=False) == "10.0.0.2"  # type: ignore[arg-type]


def test_railway_proxy_uses_overwritten_single_x_real_ip_when_enabled() -> None:
    req = SimpleNamespace(
        headers={"x-real-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    assert rl._client_ip(req, trust_railway_proxy_headers=True) == "9.9.9.9"  # type: ignore[arg-type]


def test_railway_proxy_rejects_invalid_or_multiple_x_real_ip_values() -> None:
    for x_real_ip in ("not-an-ip", "9.9.9.9, 1.1.1.1", "9.9.9.9 1.1.1.1", ""):
        req = SimpleNamespace(
            headers={"x-real-ip": x_real_ip},
            client=SimpleNamespace(host="10.0.0.2"),
        )
        assert rl._client_ip(req, trust_railway_proxy_headers=True) == "10.0.0.2"  # type: ignore[arg-type]


def test_chat_and_matches_are_exempt_from_ip_middleware() -> None:
    assert rl._is_exempt("/api/v1/health")
    assert rl._is_exempt("/api/v1/chat/sessions/primary")
    assert rl._is_exempt("/api/v1/matches/feed")
    assert rl._is_exempt("/api/v1/application-kits/jobs/abc/prepare")
    assert not rl._is_exempt("/api/v1/auth/me")
