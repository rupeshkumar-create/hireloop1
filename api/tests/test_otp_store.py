"""
Postgres-backed OTP store (HIR-46) — shared across workers/restarts.
Verified with a capturing fake connection (no DB).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hireloop_api.services import otp_store


class _FakeConn:
    def __init__(self, *, fetchrow_result: object = None) -> None:
        self.fetchrow_result = fetchrow_result
        self.executed: list[tuple[str, tuple]] = []
        self.fetched: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "OK"

    async def fetchrow(self, query: str, *args: object) -> object:
        self.fetched.append((query, args))
        return self.fetchrow_result


async def test_store_otp_upserts_and_resets_attempts() -> None:
    db = _FakeConn()
    await otp_store.store_otp(db, "+919876543210", otp_hash="h", ttl_minutes=10)  # type: ignore[arg-type]
    query, args = db.executed[0]
    assert "INSERT INTO public.otp_verifications" in query
    assert "ON CONFLICT (phone) DO UPDATE" in query
    assert "attempts = 0" in query
    assert args[0] == "+919876543210" and args[1] == "h"


async def test_seconds_since_last_send_none_when_absent() -> None:
    db = _FakeConn(fetchrow_result=None)
    assert await otp_store.seconds_since_last_send(db, "+91999") is None  # type: ignore[arg-type]


async def test_seconds_since_last_send_computes_elapsed() -> None:
    sent = datetime.now(UTC) - timedelta(seconds=12)
    db = _FakeConn(fetchrow_result={"last_sent_at": sent})
    elapsed = await otp_store.seconds_since_last_send(db, "+91999")  # type: ignore[arg-type]
    assert elapsed is not None and 11 <= elapsed <= 60


async def test_increment_attempts_returns_new_count() -> None:
    db = _FakeConn(fetchrow_result={"attempts": 3})
    assert await otp_store.increment_attempts(db, "+91999") == 3  # type: ignore[arg-type]
    assert "attempts = attempts + 1" in db.fetched[0][0]


async def test_clear_deletes_row() -> None:
    db = _FakeConn()
    await otp_store.clear(db, "+91999")  # type: ignore[arg-type]
    assert "DELETE FROM public.otp_verifications" in db.executed[0][0]


async def test_mark_sent_only_touches_timestamp_on_conflict() -> None:
    db = _FakeConn()
    await otp_store.mark_sent(db, "+91999")  # type: ignore[arg-type]
    query = db.executed[0][0]
    assert "ON CONFLICT (phone) DO UPDATE SET last_sent_at = NOW()" in query
