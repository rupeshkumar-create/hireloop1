"""Unit tests for core security controls (no DB / network required).

Covers the primitives that protect against cost-drain, webhook spoofing,
horizontal access (IDOR), and forged auth tokens. These run in the fast unit
suite so a regression in a security control fails the build immediately.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from hireloop_api import deps
from hireloop_api.config import Settings
from hireloop_api.services.rate_limit import check_rate_limit, reset_rate_limits


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "secret_key": "test-secret-key-not-for-prod",
        "service_secret": "test-service-secret-value",
        "supabase_url": "https://placeholder.supabase.co",
        "supabase_service_key": "placeholder",
        "openrouter_api_key": "placeholder",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


# ── Rate limiting (cost-drain / abuse) ────────────────────────────────────────


def test_rate_limit_blocks_after_max() -> None:
    reset_rate_limits()
    uid = str(uuid.uuid4())
    for _ in range(3):
        check_rate_limit(uid, "bucket", max_per_hour=3)  # within limit
    with pytest.raises(HTTPException) as exc:
        check_rate_limit(uid, "bucket", max_per_hour=3)  # one over
    assert exc.value.status_code == 429


def test_rate_limit_is_scoped_per_user_and_bucket() -> None:
    reset_rate_limits()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    check_rate_limit(a, "bk", max_per_hour=1)
    check_rate_limit(b, "bk", max_per_hour=1)  # different user — unaffected
    check_rate_limit(a, "other", max_per_hour=1)  # different bucket — unaffected
    with pytest.raises(HTTPException):
        check_rate_limit(a, "bk", max_per_hour=1)  # same user+bucket — blocked


# ── Webhook / service-secret auth (spoofing) ──────────────────────────────────


class _Req:
    def __init__(self, secret: str | None = None) -> None:
        self.headers: dict[str, str] = {} if secret is None else {"X-Service-Secret": secret}


@pytest.mark.asyncio
async def test_service_secret_rejects_missing_header() -> None:
    with pytest.raises(HTTPException) as exc:
        await deps.verify_service_secret(_Req(None), _settings())  # type: ignore[arg-type]
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_service_secret_rejects_wrong_value() -> None:
    with pytest.raises(HTTPException) as exc:
        await deps.verify_service_secret(_Req("wrong"), _settings())  # type: ignore[arg-type]
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_service_secret_accepts_correct_value() -> None:
    s = _settings(service_secret="the-correct-secret")
    # Must not raise.
    await deps.verify_service_secret(_Req("the-correct-secret"), s)  # type: ignore[arg-type]


# ── Ownership scoping helper (IDOR) ───────────────────────────────────────────


class _FakeDb:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "public.candidates" in query
        return self._row


@pytest.mark.asyncio
async def test_ownership_helper_404_when_no_candidate() -> None:
    with pytest.raises(HTTPException) as exc:
        await deps.get_current_candidate_id(
            {"id": str(uuid.uuid4())},
            _FakeDb(None),  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_ownership_helper_returns_candidate_id() -> None:
    cid = uuid.uuid4()
    got = await deps.get_current_candidate_id(
        {"id": str(uuid.uuid4())},
        _FakeDb({"id": cid}),  # type: ignore[arg-type]
    )
    assert got == cid


# ── Auth: forged / expired token rejection ────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 401

        def json(self) -> dict[str, object]:
            return {}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

        async def get(self, *args: object, **kwargs: object) -> _Resp:
            return _Resp()

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _Client())
    with pytest.raises(HTTPException) as exc:
        await deps._fetch_supabase_user("forged-token", _settings())
    assert exc.value.status_code == 401
