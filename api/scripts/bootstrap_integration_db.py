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

-- Stubs for Supabase RLS policies (auth.uid / auth.role) in plain Postgres CI.
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION auth.role()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.role', true), ''), 'anon');
$$;

DO $$
BEGIN
  CREATE PUBLICATION supabase_realtime;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;
END $$;
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
        already = await conn.fetchval("SELECT to_regclass('public.users') IS NOT NULL")
        if already:
            print("Schema already present — skipping migrations.")
            return

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
