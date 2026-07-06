"""
Seed rich demo candidate + recruiter accounts for local/staging QA.

DEV/STAGING ONLY — refuses when ENVIRONMENT=production.

Re-seed full marketplace (6 candidates, 5 recruiters, jobs, matches):
    .venv/bin/python scripts/seed_marketplace_demo.py

Login (enable NEXT_PUBLIC_DEV_EMAIL_LOGIN=true in app/.env.local):
    Candidate: priya.candidate@hireschema.com / DemoCandidate26!
    Recruiter: arun.recruiter@hireschema.com / DemoRecruiter26!
"""

from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.demo_candidate_fixtures import (
    demo_career_intelligence_blob,
    demo_career_profile,
)

PASSWORD = "DemoCandidate26!"
RECRUITER_PASSWORD = "DemoRecruiter26!"

CANDIDATE_EMAIL = "priya.candidate@hireschema.com"
RECRUITER_EMAIL = "arun.recruiter@hireschema.com"

CANDIDATE_USER_ID = "c1111111-1111-1111-1111-111111111111"
RECRUITER_USER_ID = "b1111111-1111-1111-1111-111111111111"
CANDIDATE_ID = "ca111111-1111-1111-1111-111111111111"
RECRUITER_ID = "b2222222-1111-1111-1111-111111111111"
COMPANY_ID = "11111111-1111-1111-1111-111111111111"
ROLE_ID = "b3333333-1111-1111-1111-111111111111"
CONV_ID = "b4444444-1111-1111-1111-111111111111"

CANDIDATE_JD_SKILLS = ["python", "fastapi", "postgres", "aws", "kubernetes", "system-design"]
CAREER_PROFILE = demo_career_profile(
    {
        "email": CANDIDATE_EMAIL,
        "current_title": "Senior Backend Engineer",
        "current_company": "Razorpay",
        "years_experience": 7,
        "city": "Bengaluru",
        "summary": "7 years building high-scale payment and API platforms in Indian fintech.",
        "skills": CANDIDATE_JD_SKILLS,
        "target_titles": ["Staff Backend Engineer", "Lead Backend Engineer"],
    }
)

RECRUITER_JD = """
Senior Backend Engineer — Acme Fintech (Bengaluru, Hybrid)

We're scaling our payments platform for 50M+ Indians. You will own core services
in Python/FastAPI, design for high availability on AWS, and mentor 2-3 engineers.

Must have:
- 5+ years backend engineering in product companies
- Strong Python, PostgreSQL, distributed systems
- Experience with payments or fintech is a plus

Compensation: Rs 35-50 LPA (fixed + variable). Bengaluru hybrid (3 days office).
"""


def _candidate_ctx() -> dict:
    return {
        "email": CANDIDATE_EMAIL,
        "full_name": "Priya Sharma",
        "current_title": "Senior Backend Engineer",
        "current_company": "Razorpay",
        "years_experience": 7,
        "city": "Bengaluru",
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "skills": CANDIDATE_JD_SKILLS,
        "headline": "Senior backend engineer · payments · Python · Bengaluru",
        "summary": "7 years building high-scale payment and API platforms in Indian fintech.",
        "expected_ctc_min": 3_500_000,
        "expected_ctc_max": 5_000_000,
        "current_ctc": 2_800_000,
        "ctc_min": 3_500_000,
        "ctc_max": 5_000_000,
        "notice_period_days": 30,
        "looking_for": "Staff/Lead backend roles at product-led fintech or B2B SaaS in Bengaluru",
        "remote_preference": "any",
        "target_titles": ["Staff Backend Engineer", "Lead Backend Engineer"],
        "career_profile": CAREER_PROFILE,
    }


async def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to seed: ENVIRONMENT=production", file=sys.stderr)
        raise SystemExit(1)

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    career_intel = demo_career_intelligence_blob(_candidate_ctx())
    completeness = career_intel.get("data_completeness", 0)

    try:
        # Remove prior demo accounts (same emails or fixed ids)
        await conn.execute(
            """
            DELETE FROM auth.users
            WHERE email IN ($1, $2)
               OR id IN ($3::uuid, $4::uuid)
            """,
            CANDIDATE_EMAIL,
            RECRUITER_EMAIL,
            CANDIDATE_USER_ID,
            RECRUITER_USER_ID,
        )

        await conn.execute(
            """
            INSERT INTO public.companies (id, name, domain, industry, size_bucket, hq_city, hq_state, country_code)
            VALUES ($1::uuid, 'Acme Fintech', 'acmefintech.in', 'Fintech', '201-500', 'Bengaluru', 'Karnataka', 'IN')
            ON CONFLICT (id) DO NOTHING
            """,
            COMPANY_ID,
        )

        # ── Auth users (email + password) ─────────────────────────────────────
        for email, password, user_id, full_name in (
            (CANDIDATE_EMAIL, PASSWORD, CANDIDATE_USER_ID, "Priya Sharma"),
            (RECRUITER_EMAIL, RECRUITER_PASSWORD, RECRUITER_USER_ID, "Arun Mehta"),
        ):
            await conn.execute(
                """
                INSERT INTO auth.users (
                  instance_id, id, aud, role, email, encrypted_password,
                  email_confirmed_at, recovery_sent_at, last_sign_in_at,
                  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
                  confirmation_token, email_change, email_change_token_new, recovery_token
                )
                VALUES (
                  '00000000-0000-0000-0000-000000000000',
                  $1::uuid, 'authenticated', 'authenticated',
                  $2, crypt($3, gen_salt('bf')),
                  NOW(), NOW(), NOW(),
                  '{"provider":"email","providers":["email"]}',
                  $4::jsonb,
                  NOW(), NOW(),
                  '', '', '', ''
                )
                """,
                user_id,
                email,
                password,
                json.dumps({"full_name": full_name}),
            )
            await conn.execute(
                """
                INSERT INTO auth.identities (
                  id, user_id, identity_data, provider, provider_id,
                  last_sign_in_at, created_at, updated_at
                )
                VALUES ($1::uuid, $1::uuid, $2::jsonb, 'email', $1::text, NOW(), NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                user_id,
                json.dumps({"sub": user_id, "email": email}),
            )

        # ── Public users ────────────────────────────────────────────────────
        await conn.execute(
            """
            INSERT INTO public.users (id, email, phone, full_name, role, phone_verified, market, phone_country)
            VALUES
              ($1::uuid, $2, '+919876543210', 'Priya Sharma', 'candidate', TRUE, 'IN', 'IN'),
              ($3::uuid, $4, '+919876543211', 'Arun Mehta', 'recruiter', TRUE, 'IN', 'IN')
            ON CONFLICT (id) DO UPDATE SET
              email = EXCLUDED.email,
              phone = EXCLUDED.phone,
              full_name = EXCLUDED.full_name,
              role = EXCLUDED.role,
              phone_verified = TRUE,
              market = 'IN',
              phone_country = 'IN',
              deleted_at = NULL,
              updated_at = NOW()
            """,
            CANDIDATE_USER_ID,
            CANDIDATE_EMAIL,
            RECRUITER_USER_ID,
            RECRUITER_EMAIL,
        )

        # ── Candidate profile (rich) ────────────────────────────────────────
        await conn.execute(
            """
            INSERT INTO public.candidates (
              id, user_id, headline, summary, current_title, current_company,
              location_city, location_state, years_experience, notice_period_days,
              expected_ctc_min, expected_ctc_max, current_ctc, skills,
              looking_for, remote_preference, profile_complete,
              career_profile, career_intelligence, career_intelligence_updated_at
            )
            VALUES (
              $1::uuid, $2::uuid, $3, $4, $5, $6,
              $7, $8, $9, $10,
              $11, $12, $13, $14::text[],
              $15, $16, TRUE,
              $17::jsonb, $18::jsonb, NOW()
            )
            ON CONFLICT (user_id) DO UPDATE SET
              headline = EXCLUDED.headline,
              summary = EXCLUDED.summary,
              current_title = EXCLUDED.current_title,
              current_company = EXCLUDED.current_company,
              location_city = EXCLUDED.location_city,
              location_state = EXCLUDED.location_state,
              years_experience = EXCLUDED.years_experience,
              notice_period_days = EXCLUDED.notice_period_days,
              expected_ctc_min = EXCLUDED.expected_ctc_min,
              expected_ctc_max = EXCLUDED.expected_ctc_max,
              current_ctc = EXCLUDED.current_ctc,
              skills = EXCLUDED.skills,
              looking_for = EXCLUDED.looking_for,
              remote_preference = EXCLUDED.remote_preference,
              profile_complete = TRUE,
              career_profile = EXCLUDED.career_profile,
              career_intelligence = EXCLUDED.career_intelligence,
              career_intelligence_updated_at = NOW(),
              deleted_at = NULL,
              updated_at = NOW()
            """,
            CANDIDATE_ID,
            CANDIDATE_USER_ID,
            "Senior backend engineer · payments · Python · Bengaluru",
            "7 years building high-scale payment and API platforms in Indian fintech.",
            "Senior Backend Engineer",
            "Razorpay",
            "Bengaluru",
            "Karnataka",
            7,
            30,
            3_500_000,
            5_000_000,
            2_800_000,
            CANDIDATE_JD_SKILLS,
            "Staff/Lead backend at product fintech or B2B SaaS (Bengaluru hybrid)",
            "any",
            json.dumps(CAREER_PROFILE),
            json.dumps(career_intel),
        )

        # ── Recruiter + role ────────────────────────────────────────────────
        await conn.execute(
            """
            INSERT INTO public.recruiters (id, user_id, company_id, title, bio)
            VALUES ($1::uuid, $2::uuid, $3::uuid, 'Talent Lead',
                    'Hiring backend engineers for Acme Fintech.')
            ON CONFLICT (user_id) DO UPDATE SET
              company_id = EXCLUDED.company_id,
              title = EXCLUDED.title,
              bio = EXCLUDED.bio,
              deleted_at = NULL,
              updated_at = NOW()
            """,
            RECRUITER_ID,
            RECRUITER_USER_ID,
            COMPANY_ID,
        )

        await conn.execute(
            """
            INSERT INTO public.roles (
              id, company_id, recruiter_id, title, jd_text, status,
              hiring_brief, candidate_pitch, comp_min, comp_max,
              location_city, location_state, remote_policy,
              must_haves, nice_to_haves, jd_structured
            )
            VALUES (
              $1::uuid, $2::uuid, $3::uuid, 'Senior Backend Engineer', $4, 'draft',
              $5, $6, $7, $8,
              'Bengaluru', 'Karnataka', 'hybrid',
              $9::jsonb, $10::jsonb, $11::jsonb
            )
            ON CONFLICT (id) DO UPDATE SET
              title = EXCLUDED.title,
              jd_text = EXCLUDED.jd_text,
              hiring_brief = EXCLUDED.hiring_brief,
              candidate_pitch = EXCLUDED.candidate_pitch,
              comp_min = EXCLUDED.comp_min,
              comp_max = EXCLUDED.comp_max,
              location_city = EXCLUDED.location_city,
              location_state = EXCLUDED.location_state,
              remote_policy = EXCLUDED.remote_policy,
              must_haves = EXCLUDED.must_haves,
              nice_to_haves = EXCLUDED.nice_to_haves,
              jd_structured = EXCLUDED.jd_structured,
              updated_at = NOW()
            """,
            ROLE_ID,
            COMPANY_ID,
            RECRUITER_ID,
            RECRUITER_JD.strip(),
            "Hire a senior backend engineer to scale payments infra. Python + Postgres required.",
            "Build India-scale payment rails at Acme Fintech — hybrid Bengaluru.",
            3_500_000,
            5_000_000,
            json.dumps(["5+ years Python", "PostgreSQL at scale", "Distributed systems", "AWS"]),
            json.dumps(["Fintech experience", "Kubernetes", "System design interviews"]),
            json.dumps(
                {
                    "seniority": "senior",
                    "years_experience_min": 5,
                    "years_experience_max": 10,
                    "comp_min_lpa": 35,
                    "comp_max_lpa": 50,
                    "comp_structure": "fixed_plus_variable",
                }
            ),
        )

        await conn.execute(
            """
            INSERT INTO public.conversations (id, recruiter_id, role_id, agent, title)
            VALUES ($1::uuid, $2::uuid, $3::uuid, 'nitya', 'Intake: Senior Backend Engineer')
            ON CONFLICT (id) DO NOTHING
            """,
            CONV_ID,
            RECRUITER_ID,
            ROLE_ID,
        )

        # Sample match scores against seed jobs if present
        await conn.execute(
            """
            INSERT INTO public.match_scores (
              candidate_id, job_id, overall_score, skills_score, experience_score,
              location_score, ctc_score, explanation
            )
            SELECT
              $1::uuid, j.id,
              0.84, 0.90, 0.82, 0.95, 0.75,
              'Strong match (84%) — Python/FastAPI align with Senior Backend roles in Bengaluru.'
            FROM public.jobs j
            WHERE j.title ILIKE '%Senior Backend%'
              AND j.deleted_at IS NULL
            LIMIT 1
            ON CONFLICT (candidate_id, job_id) DO UPDATE SET
              overall_score = EXCLUDED.overall_score,
              skills_score = EXCLUDED.skills_score,
              experience_score = EXCLUDED.experience_score,
              location_score = EXCLUDED.location_score,
              ctc_score = EXCLUDED.ctc_score,
              explanation = EXCLUDED.explanation
            """,
            CANDIDATE_ID,
        )

        print("Demo accounts seeded successfully.\n")
        print("Enable dev login in app/.env.local:")
        print("  NEXT_PUBLIC_DEV_EMAIL_LOGIN=true\n")
        print("Candidate (job seeker):")
        print(f"  Email:    {CANDIDATE_EMAIL}")
        print(f"  Password: {PASSWORD}")
        print(f"  Profile:  ~{completeness}% complete · Bengaluru · 7 YOE · ₹35-50 LPA target\n")
        print("Recruiter (hiring manager):")
        print(f"  Email:    {RECRUITER_EMAIL}")
        print(f"  Password: {RECRUITER_PASSWORD}")
        print("  Role:     Senior Backend Engineer at Acme Fintech (draft, JD filled)\n")
        print("Sign in at http://localhost:3001/signup?mode=signin")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
