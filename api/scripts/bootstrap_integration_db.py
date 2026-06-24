#!/usr/bin/env python3
"""
Bootstrap a Postgres database for integration tests.

Applies supabase migrations in order, with test-environment stubs for
Supabase-only features (auth schema, pg_cron, storage buckets).

Usage:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hireloop_test \\
    python scripts/bootstrap_integration_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"

# Migrations that require Supabase extensions / storage / cron (skipped in CI Postgres).
SKIP_MIGRATIONS = {
    "20240101000000_init_extensions.sql",
    "20240101000600_cron_jobs.sql",
    "20240101000700_storage_buckets.sql",
    "20240101000800_jobs_ingestion_cron.sql",
    "20240101000900_matching_cron.sql",
}

TEST_PRELUDE = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
  id UUID PRIMARY KEY,
  email TEXT,
  raw_user_meta_data JSONB DEFAULT '{}'::jsonb
);
"""


def _dsn() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)
    return raw.replace("postgresql+asyncpg://", "postgresql://")


async def _apply_sql(conn: asyncpg.Connection, sql: str, label: str) -> None:
    try:
        await conn.execute(sql)
    except Exception as exc:
        print(f"  FAIL {label}: {exc}", file=sys.stderr)
        raise


async def bootstrap() -> None:
    dsn = _dsn()
    conn = await asyncpg.connect(dsn)
    try:
        print("Applying test prelude (extensions + auth.users stub)…")
        await _apply_sql(conn, TEST_PRELUDE, "prelude")

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        applied = 0
        skipped = 0
        for path in files:
            if path.name in SKIP_MIGRATIONS:
                skipped += 1
                continue
            print(f"  → {path.name}")
            sql = path.read_text(encoding="utf-8")
            await _apply_sql(conn, sql, path.name)
            applied += 1

        print(f"Done: {applied} migrations applied, {skipped} skipped.")
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
