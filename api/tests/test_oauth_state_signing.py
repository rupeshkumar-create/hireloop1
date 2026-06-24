"""
Google OAuth `state` must be HMAC-signed and time-limited. The callback is
unauthenticated, so a forgeable state would let an attacker bind their own
mailbox to a victim's account.
"""

from __future__ import annotations

from hireloop_api.routes.gmail import (
    _STATE_TTL_SECONDS,
    sign_oauth_state,
    verify_oauth_state,
)

_SECRET = "test-secret"
_USER = "8b9f2f6a-1111-2222-3333-444455556666"


def test_roundtrip_verifies() -> None:
    state = sign_oauth_state(_SECRET, _USER, now=1_000_000)
    assert verify_oauth_state(_SECRET, state, now=1_000_010) == _USER


def test_raw_user_id_rejected() -> None:
    # The legacy unsigned form must never validate.
    assert verify_oauth_state(_SECRET, _USER) is None


def test_tampered_user_id_rejected() -> None:
    state = sign_oauth_state(_SECRET, _USER, now=1_000_000)
    other = "0" * 8 + state[8:]  # mutate the user-id portion, keep sig
    assert verify_oauth_state(_SECRET, other, now=1_000_010) is None


def test_wrong_secret_rejected() -> None:
    state = sign_oauth_state(_SECRET, _USER, now=1_000_000)
    assert verify_oauth_state("other-secret", state, now=1_000_010) is None


def test_expired_state_rejected() -> None:
    state = sign_oauth_state(_SECRET, _USER, now=1_000_000)
    assert verify_oauth_state(_SECRET, state, now=1_000_000 + _STATE_TTL_SECONDS + 1) is None


def test_garbage_rejected() -> None:
    assert verify_oauth_state(_SECRET, "") is None
    assert verify_oauth_state(_SECRET, "a.b") is None
    assert verify_oauth_state(_SECRET, "a.notanumber.deadbeef") is None
