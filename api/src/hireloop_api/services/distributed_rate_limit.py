"""Postgres-backed fixed-window limits for horizontally scaled public endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
from fastapi import HTTPException, status


async def check_distributed_rate_limit(
    db: asyncpg.Connection,
    *,
    identity_hash: str,
    bucket: str,
    max_per_hour: int,
) -> None:
    now = datetime.now(UTC)
    window_start = now.replace(minute=0, second=0, microsecond=0)
    count = await db.fetchval(
        """
        INSERT INTO public.api_rate_limits
          (identity_hash, bucket, window_start, request_count)
        VALUES ($1, $2, $3, 1)
        ON CONFLICT (identity_hash, bucket, window_start) DO UPDATE
        SET request_count = public.api_rate_limits.request_count + 1,
            updated_at = NOW()
        RETURNING request_count
        """,
        identity_hash,
        bucket,
        window_start,
    )
    if int(count or 0) <= max_per_hour:
        return
    retry_in = max(1, int((window_start + timedelta(hours=1) - now).total_seconds()))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Try again later.",
        headers={"Retry-After": str(retry_in)},
    )
