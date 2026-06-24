"""
Purge ALL users, auth accounts, chat memory, and candidate PII from the database.

Preserves jobs, companies, and job embeddings (market data). Re-run match
recompute after onboarding a fresh test user.

DEV/STAGING ONLY — refuses to run when ENVIRONMENT=production.

Usage (from api/):
    .venv/bin/python scripts/purge_all_users.py
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

from hireloop_api.config import get_settings

PURGE_SQL = """
BEGIN;

-- Chat + agent telemetry (conversations.role_id blocks role delete)
DELETE FROM public.messages;
DELETE FROM public.agent_actions;
DELETE FROM public.conversations;

-- FK blockers (no ON DELETE CASCADE to users/candidates)
DELETE FROM public.intro_messages;
UPDATE public.role_versions SET created_by = NULL;
DELETE FROM public.placements;
DELETE FROM public.match_audits;
DELETE FROM public.role_pipeline;
DELETE FROM public.otp_verifications;

-- Detach market jobs from recruiter-owned roles before dropping recruiters
UPDATE public.jobs SET recruiter_id = NULL, role_id = NULL
  WHERE recruiter_id IS NOT NULL OR role_id IS NOT NULL;
UPDATE public.intro_requests SET role_id = NULL, invite_id = NULL, recruiter_id = NULL;

DELETE FROM public.recruiter_invites;
DELETE FROM public.role_versions;
DELETE FROM public.roles;
DELETE FROM public.recruiter_searches;

-- Auth + public profile graph (cascades conversations, messages, memory, kits…)
DELETE FROM auth.users;

COMMIT;
"""


async def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to purge: ENVIRONMENT=production", file=sys.stderr)
        raise SystemExit(1)

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        before_auth = await conn.fetchval("SELECT count(*) FROM auth.users")
        before_public = await conn.fetchval("SELECT count(*) FROM public.users")
        before_candidates = await conn.fetchval("SELECT count(*) FROM public.candidates")
        before_recruiters = await conn.fetchval("SELECT count(*) FROM public.recruiters")
        before_roles = await conn.fetchval("SELECT count(*) FROM public.roles")
        before_conversations = await conn.fetchval("SELECT count(*) FROM public.conversations")
        before_messages = await conn.fetchval("SELECT count(*) FROM public.messages")

        print("Before purge:")
        print(f"  auth.users:      {before_auth}")
        print(f"  public.users:    {before_public}")
        print(f"  candidates:      {before_candidates}")
        print(f"  recruiters:      {before_recruiters}")
        print(f"  roles:           {before_roles}")
        print(f"  conversations:   {before_conversations}")
        print(f"  messages:        {before_messages}")

        await conn.execute(PURGE_SQL)

        after_auth = await conn.fetchval("SELECT count(*) FROM auth.users")
        after_public = await conn.fetchval("SELECT count(*) FROM public.users")
        after_candidates = await conn.fetchval("SELECT count(*) FROM public.candidates")
        after_recruiters = await conn.fetchval("SELECT count(*) FROM public.recruiters")
        after_roles = await conn.fetchval("SELECT count(*) FROM public.roles")
        after_conversations = await conn.fetchval("SELECT count(*) FROM public.conversations")
        after_messages = await conn.fetchval("SELECT count(*) FROM public.messages")
        jobs_left = await conn.fetchval("SELECT count(*) FROM public.jobs WHERE deleted_at IS NULL")

        print("\nAfter purge:")
        print(f"  auth.users:      {after_auth}")
        print(f"  public.users:    {after_public}")
        print(f"  candidates:      {after_candidates}")
        print(f"  recruiters:      {after_recruiters}")
        print(f"  roles:           {after_roles}")
        print(f"  conversations:   {after_conversations}")
        print(f"  messages:        {after_messages}")
        print(f"  active jobs:     {jobs_left} (preserved)")
        print("\nDone — sign up again with a fresh account.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
