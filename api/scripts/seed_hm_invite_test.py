"""
Seed a scraped-style job + external hiring manager for off-platform intro testing.

Flow under test:
  1. Candidate requests intro on a job with NO registered recruiter
  2. HM email is known → recruiter_invites row + transactional email to HM
  3. HM opens /recruiter/invite?token=… → onboarding → inbox → chat

HM inbox: rupesh7126@gmail.com

Run from api/:
    .venv/bin/python scripts/seed_hm_invite_test.py
    .venv/bin/python scripts/seed_hm_invite_test.py --send-intro
    .venv/bin/python scripts/seed_hm_invite_test.py --send-intro --candidate gerihaj150@kinws.com
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.email.transactional import send_recruiter_invite_email
from hireloop_api.services.embeddings import EmbeddingService
from hireloop_api.services.intro_service import create_candidate_intro
from hireloop_api.services.matching import MatchingEngine

COMPANY_ID = uuid.UUID("e1000004-0000-4000-8000-000000000004")
JOB_ID = uuid.UUID("e2000004-0000-4000-8000-000000000004")
HM_ID = uuid.UUID("e3000004-0000-4000-8000-000000000004")

HM_EMAIL = "rupesh7126@gmail.com"
HM_NAME = "Rupesh Kumar"
DEFAULT_CANDIDATE_EMAIL = "gerihaj150@kinws.com"

JOB_TITLE = "Head of Growth — Staffing SaaS (External HM Test)"
COMPANY_NAME = "Urban Ridge Supplies"


async def _upsert_company(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO public.companies (id, name, industry, size_bucket)
        VALUES ($1, $2, 'Staffing & Recruiting', '51-200')
        ON CONFLICT (id) DO UPDATE SET
          name = EXCLUDED.name,
          updated_at = NOW()
        """,
        COMPANY_ID,
        COMPANY_NAME,
    )


async def _upsert_hiring_manager(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO public.hiring_managers (
          id, company_id, full_name, title, email, email_verified, enrich_status
        )
        VALUES ($1, $2, $3, 'Head of Talent', $4, TRUE, 'done')
        ON CONFLICT (id) DO UPDATE SET
          company_id = EXCLUDED.company_id,
          full_name = EXCLUDED.full_name,
          title = EXCLUDED.title,
          email = EXCLUDED.email,
          email_verified = TRUE,
          enrich_status = 'done',
          updated_at = NOW()
        """,
        HM_ID,
        COMPANY_ID,
        HM_NAME,
        HM_EMAIL,
    )


async def _upsert_job(conn: asyncpg.Connection) -> None:
    """Scraped job — recruiter_id NULL so intro routes to HM invite email."""
    jd = """
Head of Growth — Staffing SaaS (Bengaluru, hybrid)

Urban Ridge Supplies is hiring a Head of Growth to scale a B2B staffing / resume-tech
platform across India. This is a test listing for the external hiring-manager intro flow.

What you'll do:
- Own pipeline generation, PLG loops, and recruiter-side activation
- Partner with product on AI resume builder positioning
- Build GTM experiments across LinkedIn, outbound, and partnerships

Must have: 8+ years growth/GTM, B2B SaaS, staffing or HR-tech exposure.
Comp: ₹35–50 LPA. Hybrid in Bengaluru.
""".strip()

    await conn.execute(
        """
        INSERT INTO public.jobs (
          id, company_id, recruiter_id, role_id, title, description,
          location_city, location_state, country_code,
          is_remote, employment_type, seniority,
          ctc_min, ctc_max, skills_required,
          apify_job_id, source, is_active, scraped_at, expires_at, apply_url
        )
        VALUES (
          $1, $2, NULL, NULL, $3, $4,
          'Bengaluru', 'Karnataka', 'IN',
          FALSE, 'full_time', 'lead',
          3_500_000, 5_000_000,
          ARRAY['growth', 'gtm', 'b2b saas', 'staffing', 'hr tech', 'plg'],
          'seed-hm-invite-test-urban-ridge', 'manual', TRUE,
          NOW(), NOW() + INTERVAL '90 days',
          'https://example.com/apply/urban-ridge-growth'
        )
        ON CONFLICT (id) DO UPDATE SET
          company_id = EXCLUDED.company_id,
          recruiter_id = NULL,
          role_id = NULL,
          title = EXCLUDED.title,
          description = EXCLUDED.description,
          location_city = EXCLUDED.location_city,
          ctc_min = EXCLUDED.ctc_min,
          ctc_max = EXCLUDED.ctc_max,
          skills_required = EXCLUDED.skills_required,
          is_active = TRUE,
          expires_at = NOW() + INTERVAL '90 days',
          updated_at = NOW()
        """,
        JOB_ID,
        COMPANY_ID,
        JOB_TITLE,
        jd,
    )


async def _candidate_user_id(conn: asyncpg.Connection, email: str) -> str | None:
    return await conn.fetchval(
        """
        SELECT u.id::text FROM public.users u
        JOIN public.candidates c ON c.user_id = u.id AND c.deleted_at IS NULL
        WHERE u.email = $1 AND u.deleted_at IS NULL
        """,
        email,
    )


async def _latest_invite_token(conn: asyncpg.Connection, candidate_email: str) -> str | None:
    return await conn.fetchval(
        """
        SELECT inv.token
        FROM public.recruiter_invites inv
        JOIN public.candidates c ON c.id = inv.candidate_id
        JOIN public.users u ON u.id = c.user_id
        WHERE inv.job_id = $1::uuid
          AND u.email = $2
          AND inv.email = $3
        ORDER BY inv.sent_at DESC NULLS LAST
        LIMIT 1
        """,
        JOB_ID,
        candidate_email,
        HM_EMAIL,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed external HM intro test job")
    parser.add_argument(
        "--resend-email",
        action="store_true",
        help="Resend invite email for the latest invite on this job (no new intro row)",
    )
    parser.add_argument(
        "--send-intro",
        action="store_true",
        help="Trigger candidate intro (sends invite email to HM if email is configured)",
    )
    parser.add_argument(
        "--candidate",
        default=DEFAULT_CANDIDATE_EMAIL,
        help=f"Candidate email for --send-intro (default: {DEFAULT_CANDIDATE_EMAIL})",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        await _upsert_company(conn)
        await _upsert_hiring_manager(conn)
        await _upsert_job(conn)

        embedder = EmbeddingService(settings.openrouter_api_key or "", conn)
        engine = MatchingEngine(conn)
        await embedder.embed_job(str(JOB_ID))
        await engine.score_job(str(JOB_ID), notify=False)

        print("✓ External HM intro test data ready\n")
        print(f"  Company:  {COMPANY_NAME} ({COMPANY_ID})")
        print(f"  Job:      {JOB_TITLE}")
        print(f"  Job ID:   {JOB_ID}")
        print(f"  HM:       {HM_NAME} <{HM_EMAIL}> ({HM_ID})")
        print("  Note:     recruiter_id is NULL — intro emails HM, not in-app recruiter\n")

        user_id = await _candidate_user_id(conn, args.candidate)
        if not user_id:
            print(f"WARN: candidate {args.candidate} not found — skip --send-intro")
        elif args.resend_email:
            row = await conn.fetchrow(
                """
                SELECT inv.token, u.full_name AS candidate_name, j.title AS job_title
                FROM public.recruiter_invites inv
                JOIN public.jobs j ON j.id = inv.job_id
                JOIN public.candidates c ON c.id = inv.candidate_id
                JOIN public.users u ON u.id = c.user_id
                WHERE inv.job_id = $1::uuid AND inv.email = $2
                ORDER BY inv.sent_at DESC NULLS LAST
                LIMIT 1
                """,
                JOB_ID,
                HM_EMAIL,
            )
            if not row:
                print("No invite found — run with --send-intro first")
            else:
                base = settings.public_app_url.rstrip("/")
                cta = f"{base}/recruiter/invite?token={row['token']}"
                sent = await send_recruiter_invite_email(
                    settings,
                    to_email=HM_EMAIL,
                    invited_name=HM_NAME,
                    candidate_name=row["candidate_name"] or "A candidate",
                    job_title=row["job_title"] or JOB_TITLE,
                    cta_url=cta,
                )
                print(f"Email sent: {sent}")
                if not sent:
                    print(
                        "\nTo send from the same address as signup OTP (e.g. rupesh.kumar@candidate.ly), "
                        "add to api/.env:\n"
                        "  RESEND_API_KEY=<copy from Supabase → Authentication → SMTP → Password>\n"
                        "  RESEND_FROM_EMAIL=rupesh.kumar@candidate.ly\n"
                        "  RESEND_FROM_NAME=Hireschema"
                    )
                print(f"Invite link:\n  {cta}")
        elif args.send_intro:
            result = await create_candidate_intro(
                conn,
                user_id=user_id,
                job_id=str(JOB_ID),
                hiring_manager_id=str(HM_ID),
                message="I'd love to explore the Head of Growth role at Urban Ridge Supplies.",
            )
            print("Intro result:", result)
            token = await _latest_invite_token(conn, args.candidate)
            if token:
                base = settings.public_app_url.rstrip("/")
                print(
                    f"\nInvite link (for manual test if email didn't send):\n  {base}/recruiter/invite?token={token}"
                )
        else:
            print("To send the HM invite email, re-run with:  --send-intro")
            print(
                f"  Example: .venv/bin/python scripts/seed_hm_invite_test.py --send-intro --candidate {args.candidate}"
            )
            print("\nOr ask Aarya as the candidate:")
            print(f'  "Request an intro for job {JOB_ID}"')
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
