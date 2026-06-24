#!/usr/bin/env python3
"""
Verify Supabase cloud connection: API keys, storage buckets, DB (optional).

Reads api/.env and app/.env.local (via dotenv-style parse).
Exit 0 = all checks passed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_config() -> dict[str, str]:
    api = parse_env(ROOT / "api" / ".env")
    app = parse_env(ROOT / "app" / ".env.local")
    return {**app, **api}


async def check_db(dsn: str) -> tuple[bool, str]:
    try:
        import asyncpg
    except ImportError:
        return False, "asyncpg not installed (pip install asyncpg in api venv)"

    pg_dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = await asyncpg.connect(pg_dsn, timeout=15)
        row = await conn.fetchrow(
            "SELECT COUNT(*)::int AS n FROM storage.buckets WHERE id IN ('resumes','avatars','tailored-resumes')"
        )
        await conn.close()
        n = row["n"] if row else 0
        if n >= 3:
            return True, f"DB OK — {n}/3 storage buckets found"
        return False, f"DB connected but only {n}/3 buckets (run: supabase db push)"
    except Exception as e:
        return False, f"DB failed: {e}"


async def check_storage(url: str, service_key: str) -> tuple[bool, str]:
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{url.rstrip('/')}/storage/v1/bucket", headers=headers)
        if r.status_code != 200:
            return False, f"Storage API {r.status_code}: {r.text[:200]}"
        buckets = {b.get("id") for b in r.json()}
        required = {"resumes", "avatars", "tailored-resumes"}
        missing = required - buckets
        if missing:
            return False, f"Missing buckets: {missing} — run supabase db push"
        return True, f"Storage OK — buckets: {', '.join(sorted(required))}"


async def check_auth(url: str, anon_key: str) -> tuple[bool, str]:
    headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{url.rstrip('/')}/auth/v1/health", headers=headers)
        if r.status_code == 200:
            return True, "Auth API reachable"
        # Some projects return 401 without session — still means URL/key shape is valid
        if r.status_code in (401, 404):
            r2 = await client.get(
                f"{url.rstrip('/')}/auth/v1/settings",
                headers=headers,
            )
            if r2.status_code == 200:
                return True, "Auth settings reachable"
        return False, f"Auth check failed {r.status_code}: {r.text[:200]}"


async def main() -> int:
    cfg = load_config()
    url = cfg.get("SUPABASE_URL") or cfg.get("NEXT_PUBLIC_SUPABASE_URL", "")
    anon = cfg.get("SUPABASE_ANON_KEY") or cfg.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    service = cfg.get("SUPABASE_SERVICE_KEY", "")
    dsn = cfg.get("DATABASE_URL", "")

    if not url or "your-project" in url:
        print("FAIL: Supabase URL not configured. Run scripts/configure_supabase.py first.")
        return 1

    print(f"Project URL: {url}\n")
    ok = True

    if anon and "your-anon" not in anon:
        passed, msg = await check_auth(url, anon)
        print(("PASS" if passed else "FAIL") + f" — {msg}")
        ok = ok and passed
    else:
        print("SKIP — anon key missing")
        ok = False

    if service and "your-service" not in service:
        passed, msg = await check_storage(url, service)
        print(("PASS" if passed else "FAIL") + f" — {msg}")
        ok = ok and passed
    else:
        print("SKIP — service role key missing")
        ok = False

    if dsn and "localhost:54322" not in dsn:
        passed, msg = await check_db(dsn)
        print(("PASS" if passed else "FAIL") + f" — {msg}")
        ok = ok and passed
    else:
        print("SKIP — cloud DATABASE_URL not set (still on local Supabase)")

    if ok:
        print("\nAll checks passed. Start API + app and test LinkedIn signup.")
    else:
        print("\nFix failures above, then re-run this script.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
