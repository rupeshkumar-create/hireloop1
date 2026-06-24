#!/usr/bin/env python3
"""
Delete all app users and Supabase Auth accounts for a clean testing slate.

Keeps jobs, companies, and other non-user seed data.

Usage (from repo root):
  cd api && uv run python ../scripts/reset_all_users.py

Requires DATABASE_URL and SUPABASE_URL + SUPABASE_SERVICE_KEY in api/.env
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg
import httpx

# Allow importing hireloop_api when run from api/
_api_dir = Path(__file__).resolve().parents[1] / "api"
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from hireloop_api.config import get_settings  # noqa: E402


async def _purge_public_users(conn: asyncpg.Connection) -> int:
    async with conn.transaction():
        await conn.execute("DELETE FROM public.placements")
        await conn.execute(
            """
            UPDATE public.role_versions
            SET created_by = NULL
            WHERE created_by IS NOT NULL
            """
        )
        result = await conn.execute("DELETE FROM public.users")
    # "DELETE N" -> extract count
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def _purge_auth_users(settings) -> int:
    if not settings.supabase_url or not settings.supabase_service_key:
        print("Skipping auth.users: SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        return 0

    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    deleted = 0
    page = 1
    per_page = 200

    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            resp = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
                headers=headers,
                params={"page": page, "per_page": per_page},
            )
            resp.raise_for_status()
            payload = resp.json()
            users = payload.get("users") if isinstance(payload, dict) else payload
            if not isinstance(users, list) or not users:
                break

            for user in users:
                uid = user.get("id")
                if not uid:
                    continue
                del_resp = await client.delete(
                    f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{uid}",
                    headers=headers,
                )
                if del_resp.status_code in (200, 204):
                    deleted += 1
                else:
                    print(
                        f"Warning: could not delete auth user {uid}: "
                        f"{del_resp.status_code} {del_resp.text[:200]}"
                    )

            if len(users) < per_page:
                break
            page += 1

    return deleted


async def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set in api/.env")
        return 1

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        public_deleted = await _purge_public_users(conn)
        print(f"Deleted {public_deleted} row(s) from public.users (cascaded PII).")
    finally:
        await conn.close()

    auth_deleted = await _purge_auth_users(settings)
    print(f"Deleted {auth_deleted} Supabase Auth user(s).")
    print("Done. Jobs and companies were left intact for matching tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
