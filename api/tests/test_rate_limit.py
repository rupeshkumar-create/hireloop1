"""In-process rate limiter (fixed-window, per IP)."""

from __future__ import annotations

import hireloop_api.rate_limit as rl


def setup_function() -> None:
    rl._buckets.clear()


def test_allows_under_limit_then_blocks_over() -> None:
    t = 1_000_000.0  # fixed window
    # General path: first _DEFAULT_MAX requests allowed, next blocked.
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


def test_window_resets_and_ips_isolated() -> None:
    t = 3_000_000.0
    for _ in range(rl._DEFAULT_MAX):
        rl.check_rate_limit("5.5.5.5", "/api/v1/x", now=t)
    assert rl.check_rate_limit("5.5.5.5", "/api/v1/x", now=t)[0] is False
    # A different IP is unaffected.
    assert rl.check_rate_limit("6.6.6.6", "/api/v1/x", now=t)[0] is True
    # Next window resets the original IP.
    assert rl.check_rate_limit("5.5.5.5", "/api/v1/x", now=t + rl._WINDOW_SECONDS)[0] is True
