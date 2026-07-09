"""
Postgres-backed phone-OTP store — shared across API workers and restarts (HIR-46).

Replaces the in-process dict so OTP state (hash, expiry, attempts, resend
cooldown) is consistent behind multiple workers / a load balancer, instead of
living in one process's memory. All values are server-written; the table is
service-role only (RLS on, no policies). Codes are stored hashed (keyed HMAC),
never plaintext.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg


async def seconds_since_last_send(db: asyncpg.Connection, phone: str) -> float | None:
    """Seconds since the last OTP send for resend-cooldown, or None if never sent."""
    row = await db.fetchrow(
        "SELECT last_sent_at FROM public.otp_verifications WHERE phone = $1",
        phone,
    )
    if not row or row["last_sent_at"] is None:
        return None
    return (datetime.now(UTC) - row["last_sent_at"]).total_seconds()


async def store_otp(db: asyncpg.Connection, phone: str, *, otp_hash: str, ttl_minutes: int) -> None:
    """Persist a freshly issued OTP hash; resets attempts and the send timestamp."""
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    await db.execute(
        """
        INSERT INTO public.otp_verifications (phone, otp_hash, expires_at, attempts, last_sent_at)
        VALUES ($1, $2, $3, 0, NOW())
        ON CONFLICT (phone) DO UPDATE SET
          otp_hash = EXCLUDED.otp_hash,
          expires_at = EXCLUDED.expires_at,
          attempts = 0,
          last_sent_at = NOW()
        """,
        phone,
        otp_hash,
        expires_at,
    )


async def mark_sent(db: asyncpg.Connection, phone: str) -> None:
    """Record a send timestamp for resend cooldown tracking."""
    await db.execute(
        """
        INSERT INTO public.otp_verifications (phone, otp_hash, expires_at, attempts, last_sent_at)
        VALUES ($1, '', NOW(), 0, NOW())
        ON CONFLICT (phone) DO UPDATE SET last_sent_at = NOW()
        """,
        phone,
    )


async def get_active(db: asyncpg.Connection, phone: str) -> asyncpg.Record | None:
    """The stored OTP row (otp_hash, expires_at, attempts), or None."""
    return await db.fetchrow(
        "SELECT otp_hash, expires_at, attempts FROM public.otp_verifications WHERE phone = $1",
        phone,
    )


async def increment_attempts(db: asyncpg.Connection, phone: str) -> int:
    """Atomically bump the failed-attempt counter; returns the new count."""
    row = await db.fetchrow(
        "UPDATE public.otp_verifications SET attempts = attempts + 1 "
        "WHERE phone = $1 RETURNING attempts",
        phone,
    )
    return int(row["attempts"]) if row else 0


async def clear(db: asyncpg.Connection, phone: str) -> None:
    """Remove the OTP row (on success, expiry, or attempt exhaustion)."""
    await db.execute("DELETE FROM public.otp_verifications WHERE phone = $1", phone)
