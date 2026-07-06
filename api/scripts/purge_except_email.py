"""
Delete every user except one keep-email account (and that user's graph).

DEV/STAGING ONLY — refuses when ENVIRONMENT=production.

Usage (from api/):
    .venv/bin/python scripts/purge_except_email.py
    .venv/bin/python scripts/purge_except_email.py --email rupesh.kumar@candidate.ly
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

from hireloop_api.config import get_settings

DEFAULT_KEEP_EMAIL = "rupesh.kumar@candidate.ly"


async def purge_except(conn: asyncpg.Connection, keep_email: str) -> None:
    keep_id = await conn.fetchval(
        "SELECT id FROM auth.users WHERE lower(email) = lower($1)",
        keep_email,
    )
    if not keep_id:
        raise SystemExit(f"Keep user not found in auth.users: {keep_email}")

    keep_recruiter_id = await conn.fetchval(
        "SELECT id FROM public.recruiters WHERE user_id = $1::uuid",
        keep_id,
    )

    delete_ids = [
        r["id"]
        for r in await conn.fetch(
            "SELECT id FROM auth.users WHERE id != $1::uuid",
            keep_id,
        )
    ]

    before_auth = await conn.fetchval("SELECT count(*) FROM auth.users")
    before_public = await conn.fetchval("SELECT count(*) FROM public.users")
    before_jobs = await conn.fetchval("SELECT count(*) FROM public.jobs WHERE deleted_at IS NULL")
    print(f"Keeping: {keep_email} ({keep_id})")
    if keep_recruiter_id:
        print(f"Keeping recruiter jobs for recruiter_id={keep_recruiter_id}")
    print(f"Removing {len(delete_ids)} other auth user(s)")
    print("Before:")
    print(f"  auth.users:   {before_auth}")
    print(f"  public.users: {before_public}")
    print(f"  active jobs:  {before_jobs}")

    if not delete_ids:
        print("\nNo other users to remove.")
        return

    async with conn.transaction():
        # mock_interviews.conversation_id has no ON DELETE CASCADE.
        await conn.execute(
            """
            UPDATE public.mock_interviews
            SET conversation_id = NULL
            WHERE conversation_id IN (
              SELECT conv.id
              FROM public.conversations conv
              LEFT JOIN public.candidates c ON c.id = conv.candidate_id
              LEFT JOIN public.recruiters r ON r.id = conv.recruiter_id
              WHERE conv.user_id = ANY($1::uuid[])
                 OR c.user_id = ANY($1::uuid[])
                 OR r.user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.mock_interviews
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )

        # Chat + agent telemetry for users being removed.
        await conn.execute(
            """
            DELETE FROM public.messages
            WHERE conversation_id IN (
              SELECT conv.id
              FROM public.conversations conv
              LEFT JOIN public.candidates c ON c.id = conv.candidate_id
              LEFT JOIN public.recruiters r ON r.id = conv.recruiter_id
              WHERE conv.user_id = ANY($1::uuid[])
                 OR c.user_id = ANY($1::uuid[])
                 OR r.user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            "DELETE FROM public.agent_actions WHERE user_id = ANY($1::uuid[])",
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.conversations
            WHERE user_id = ANY($1::uuid[])
            OR candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            OR recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )

        # FK blockers before recruiter/candidate graph removal.
        await conn.execute(
            """
            DELETE FROM public.intro_messages
            WHERE sender_user_id = ANY($1::uuid[])
            OR intro_request_id IN (
              SELECT ir.id
              FROM public.intro_requests ir
              LEFT JOIN public.candidates c ON c.id = ir.candidate_id
              LEFT JOIN public.recruiters rec ON rec.id = ir.recruiter_id
              WHERE c.user_id = ANY($1::uuid[])
                 OR rec.user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            UPDATE public.role_versions
            SET created_by = NULL
            WHERE created_by = ANY($1::uuid[])
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.placements
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.match_audits
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.role_pipeline
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            OR role_id IN (
              SELECT ro.id
              FROM public.roles ro
              JOIN public.recruiters rec ON rec.id = ro.recruiter_id
              WHERE rec.user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.otp_verifications
            WHERE phone IN (
              SELECT phone FROM public.users
              WHERE id = ANY($1::uuid[]) AND phone IS NOT NULL
            )
            """,
            delete_ids,
        )

        # Drop scraped market jobs and recruiter-posted jobs not owned by keep user.
        await conn.execute(
            """
            UPDATE public.recruiter_invites
            SET job_id = NULL
            WHERE job_id IN (
              SELECT id FROM public.jobs
              WHERE $1::uuid IS NULL
                 OR recruiter_id IS DISTINCT FROM $1::uuid
                 OR recruiter_id IS NULL
            )
            """,
            keep_recruiter_id,
        )
        jobs_removed = await conn.execute(
            """
            DELETE FROM public.jobs
            WHERE $1::uuid IS NULL
               OR recruiter_id IS DISTINCT FROM $1::uuid
               OR recruiter_id IS NULL
            """,
            keep_recruiter_id,
        )
        print(f"Removed jobs: {jobs_removed}")

        # Detach any remaining recruiter-owned jobs before dropping other recruiters' roles.
        await conn.execute(
            """
            UPDATE public.jobs
            SET recruiter_id = NULL, role_id = NULL
            WHERE recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            OR role_id IN (
              SELECT ro.id
              FROM public.roles ro
              JOIN public.recruiters rec ON rec.id = ro.recruiter_id
              WHERE rec.user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            UPDATE public.intro_requests
            SET role_id = NULL, invite_id = NULL, recruiter_id = NULL
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            OR recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.recruiter_invites
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            OR recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.role_versions
            WHERE role_id IN (
              SELECT ro.id
              FROM public.roles ro
              JOIN public.recruiters rec ON rec.id = ro.recruiter_id
              WHERE rec.user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.roles
            WHERE recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )
        await conn.execute(
            """
            DELETE FROM public.recruiter_searches
            WHERE recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )

        # Remove intro rows tied to deleted users (kept-user intros stay).
        await conn.execute(
            """
            DELETE FROM public.intro_requests
            WHERE candidate_id IN (
              SELECT id FROM public.candidates WHERE user_id = ANY($1::uuid[])
            )
            OR recruiter_id IN (
              SELECT id FROM public.recruiters WHERE user_id = ANY($1::uuid[])
            )
            """,
            delete_ids,
        )

        # Drop auth accounts — cascades public.users → candidates/recruiters/etc.
        await conn.execute(
            "DELETE FROM auth.users WHERE id = ANY($1::uuid[])",
            delete_ids,
        )

    after_auth = await conn.fetchval("SELECT count(*) FROM auth.users")
    after_public = await conn.fetchval("SELECT count(*) FROM public.users")
    after_candidates = await conn.fetchval("SELECT count(*) FROM public.candidates")
    after_recruiters = await conn.fetchval("SELECT count(*) FROM public.recruiters")
    after_roles = await conn.fetchval("SELECT count(*) FROM public.roles")
    jobs_left = await conn.fetchval("SELECT count(*) FROM public.jobs WHERE deleted_at IS NULL")

    print("\nAfter:")
    print(f"  auth.users:   {after_auth}")
    print(f"  public.users: {after_public}")
    print(f"  candidates:   {after_candidates}")
    print(f"  recruiters:   {after_recruiters}")
    print(f"  roles:        {after_roles}")
    print(f"  active jobs:  {jobs_left} (kept recruiter jobs only)")
    print(f"\nDone — only {keep_email} remains.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Purge all users except one email.")
    parser.add_argument("--email", default=DEFAULT_KEEP_EMAIL, help="Account to keep")
    args = parser.parse_args()

    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to purge: ENVIRONMENT=production", file=sys.stderr)
        raise SystemExit(1)

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        await purge_except(conn, args.email.strip())
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
