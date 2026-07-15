"""
User row reads/writes via Supabase PostgREST (service role).

Used when direct Postgres (asyncpg) is unavailable — e.g. wrong pooler password
in DATABASE_URL while SUPABASE_SERVICE_KEY is still valid.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog

from hireloop_api.config import Settings

logger = structlog.get_logger()


def _headers(settings: Settings) -> dict[str, str]:
    key = settings.supabase_service_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _base(settings: Settings) -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1"


async def fetch_user(settings: Settings, user_id: uuid.UUID | str) -> dict[str, Any] | None:
    """Return public.users row as dict, or None if missing."""
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    uid = str(user_id)
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.get(
            f"{_base(settings)}/users",
            params={"id": f"eq.{uid}", "deleted_at": "is.null", "select": "*"},
            headers=_headers(settings),
        )
    if resp.status_code != 200:
        logger.warning(
            "supabase_rest_fetch_user_failed",
            status=resp.status_code,
            body=resp.text[:200],
        )
        return None
    rows = resp.json()
    if not rows:
        return None
    row = rows[0]
    return {
        "id": str(row["id"]),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "full_name": row.get("full_name"),
        "avatar_url": row.get("avatar_url"),
        "role": row.get("role") or "candidate",
        "phone_verified": bool(row.get("phone_verified")),
    }


async def provision_user(
    settings: Settings, supabase_user: dict[str, Any]
) -> dict[str, Any] | None:
    """Mirror on_auth_user_created trigger — insert public.users if missing."""
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    user_id = str(supabase_user["id"])
    email = str(supabase_user.get("email") or "")
    meta = supabase_user.get("user_metadata") or {}
    role = meta.get("role") or "candidate"
    if role not in ("candidate", "recruiter"):
        role = "candidate"
    full_name = (
        meta.get("full_name") or meta.get("name") or (email.split("@", 1)[0] if email else "")
    )
    avatar = meta.get("avatar_url") or meta.get("picture")

    payload = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "avatar_url": avatar,
        "role": role,
        "phone_verified": False,
    }
    headers = _headers(settings)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"{_base(settings)}/users",
            headers=headers,
            json=payload,
        )
    if resp.status_code not in (200, 201):
        logger.warning(
            "supabase_rest_provision_failed",
            status=resp.status_code,
            body=resp.text[:300],
        )
        return await fetch_user(settings, user_id)
    rows = resp.json()
    if not rows:
        return await fetch_user(settings, user_id)
    row = rows[0] if isinstance(rows, list) else rows
    return {
        "id": str(row["id"]),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "full_name": row.get("full_name"),
        "avatar_url": row.get("avatar_url"),
        "role": row.get("role") or "candidate",
        "phone_verified": bool(row.get("phone_verified")),
    }


async def save_phone(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    phone: str,
    supabase_user: dict[str, Any],
    phone_verified: bool = True,
) -> None:
    """Upsert user row and set phone + phone_verified (OTP deferred)."""
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("Supabase REST not configured")

    existing = await fetch_user(settings, user_id)
    if not existing:
        existing = await provision_user(settings, supabase_user)
    if not existing:
        raise RuntimeError("Could not provision user row")

    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.patch(
            f"{_base(settings)}/users",
            params={"id": f"eq.{user_id}", "deleted_at": "is.null"},
            headers=_headers(settings),
            json={"phone": phone, "phone_verified": phone_verified},
        )
    if resp.status_code == 409 or "duplicate key" in resp.text.lower():
        raise ValueError("phone_already_claimed")
    if resp.status_code not in (200, 204):
        logger.error(
            "supabase_rest_save_phone_failed",
            status=resp.status_code,
            body=resp.text[:300],
        )
        raise RuntimeError(f"save phone failed: {resp.status_code}")


async def log_consent_rest(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    purpose: str,
    granted: bool = True,
) -> None:
    if not settings.supabase_url or not settings.supabase_service_key:
        return
    async with httpx.AsyncClient(timeout=15.0) as http:
        await http.post(
            f"{_base(settings)}/consent_log",
            headers=_headers(settings),
            json={
                "user_id": str(user_id),
                "purpose": purpose,
                "granted": granted,
            },
        )


async def fetch_candidate(settings: Settings, user_id: uuid.UUID | str) -> dict[str, Any] | None:
    if not settings.supabase_url or not settings.supabase_service_key:
        return None
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.get(
            f"{_base(settings)}/candidates",
            params={
                "user_id": f"eq.{user_id}",
                "deleted_at": "is.null",
                "select": "id,user_id,looking_for,headline",
            },
            headers=_headers(settings),
        )
    if resp.status_code != 200:
        return None
    rows = resp.json()
    return rows[0] if rows else None


async def ensure_candidate(
    settings: Settings,
    user_id: uuid.UUID | str,
    *,
    headline: str = "New candidate",
) -> dict[str, Any]:
    existing = await fetch_candidate(settings, user_id)
    if existing:
        return existing
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"{_base(settings)}/candidates",
            headers={**_headers(settings), "Prefer": "return=representation"},
            json={
                "user_id": str(user_id),
                "headline": headline,
                "profile_complete": False,
            },
        )
    if resp.status_code not in (200, 201):
        logger.warning(
            "supabase_rest_ensure_candidate_failed",
            status=resp.status_code,
            body=resp.text[:300],
        )
        again = await fetch_candidate(settings, user_id)
        if again:
            return again
        raise RuntimeError(f"ensure candidate failed: {resp.status_code}")
    rows = resp.json()
    return rows[0] if isinstance(rows, list) else rows


async def patch_candidate(
    settings: Settings,
    candidate_id: uuid.UUID | str,
    fields: dict[str, Any],
) -> None:
    if not fields:
        return
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.patch(
            f"{_base(settings)}/candidates",
            params={"id": f"eq.{candidate_id}", "deleted_at": "is.null"},
            headers=_headers(settings),
            json=fields,
        )
    if resp.status_code not in (200, 204):
        logger.error(
            "supabase_rest_patch_candidate_failed",
            status=resp.status_code,
            body=resp.text[:300],
        )
        raise RuntimeError(f"patch candidate failed: {resp.status_code}")


async def patch_user(
    settings: Settings,
    user_id: uuid.UUID | str,
    fields: dict[str, Any],
) -> None:
    if not fields:
        return
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.patch(
            f"{_base(settings)}/users",
            params={"id": f"eq.{user_id}", "deleted_at": "is.null"},
            headers=_headers(settings),
            json=fields,
        )
    if resp.status_code not in (200, 204):
        logger.error(
            "supabase_rest_patch_user_failed",
            status=resp.status_code,
            body=resp.text[:300],
        )
        raise RuntimeError(f"patch user failed: {resp.status_code}")
