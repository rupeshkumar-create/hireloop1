"""DPDP consent_log helpers — consistent IP/UA capture."""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import Request


def client_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return ip, ua


async def log_consent(
    db: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    purpose: str,
    granted: bool,
    request: Request | None = None,
) -> None:
    ip, ua = client_meta(request)
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted, ip_address, user_agent)
        VALUES ($1::uuid, $2, $3, $4::inet, $5)
        """,
        user_id,
        purpose,
        granted,
        ip,
        ua,
    )
