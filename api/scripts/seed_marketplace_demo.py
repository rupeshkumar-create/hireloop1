"""
Seed a rich demo marketplace: mid-career candidates, recruiters, trending jobs,
match scores, and recruiter pipelines.

DEV/STAGING ONLY — refuses when ENVIRONMENT=production.

Usage (from api/):
    .venv/bin/python scripts/seed_marketplace_demo.py

Enable dev login in app/.env.local:
    NEXT_PUBLIC_DEV_EMAIL_LOGIN=true
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import asyncpg
import httpx

from hireloop_api.config import get_settings
from hireloop_api.services.apify.job_ingester import JobIngester
from hireloop_api.services.demo_candidate_fixtures import (
    demo_candidate_context,
    demo_career_intelligence_blob,
    demo_career_profile,
    demo_parsed_resume,
)
from hireloop_api.services.intro_service import publish_role_to_jobs
from hireloop_api.services.matching import MatchingEngine, rank_candidates_for_job

CANDIDATE_PASSWORD = "DemoCandidate26!"
RECRUITER_PASSWORD = "DemoRecruiter26!"

# Mid-career trending roles for live Apify ingest (Fantastic.jobs + optional LinkedIn)
LIVE_JOB_QUERIES = [
    "Senior Backend Engineer",
    "Machine Learning Engineer",
    "Product Manager",
    "Growth Marketing Manager",
    "Full Stack Engineer",
    "DevOps Engineer",
    "Frontend Engineer",
    "Data Scientist",
]
LIVE_JOB_LOCATIONS = ["Bengaluru", "Mumbai", "Hyderabad", "India"]

DEMO_EMAILS = [
    "priya.candidate@hireschema.com",
    "rahul.candidate@hireschema.com",
    "ananya.candidate@hireschema.com",
    "vikram.candidate@hireschema.com",
    "meera.candidate@hireschema.com",
    "karan.candidate@hireschema.com",
    "arun.recruiter@hireschema.com",
    "neha.recruiter@hireschema.com",
    "sanjay.recruiter@hireschema.com",
    "divya.recruiter@hireschema.com",
    "ravi.recruiter@hireschema.com",
]

COMPANIES = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Acme Fintech",
        "domain": "acmefintech.in",
        "industry": "Fintech",
        "size": "201-500",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
    {
        "id": "d1111111-1111-1111-1111-111111111111",
        "name": "Swiggy AI Lab",
        "domain": "swiggy.in",
        "industry": "Food Tech / AI",
        "size": "1000+",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
    {
        "id": "d2222222-1111-1111-1111-111111111111",
        "name": "CRED",
        "domain": "cred.club",
        "industry": "Fintech",
        "size": "501-1000",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
    {
        "id": "d3333333-1111-1111-1111-111111111111",
        "name": "Dunzo",
        "domain": "dunzo.com",
        "industry": "Quick Commerce",
        "size": "501-1000",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
    {
        "id": "d4444444-1111-1111-1111-111111111111",
        "name": "Postman",
        "domain": "postman.com",
        "industry": "Developer Tools",
        "size": "501-1000",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
]

CANDIDATES = [
    {
        "user_id": "c1111111-1111-1111-1111-111111111111",
        "candidate_id": "ca111111-1111-1111-1111-111111111111",
        "email": "priya.candidate@hireschema.com",
        "phone": "+919876543210",
        "full_name": "Priya Sharma",
        "headline": "Senior backend engineer · payments · Python · Bengaluru",
        "summary": "7 years building high-scale payment and API platforms in Indian fintech.",
        "current_title": "Senior Backend Engineer",
        "current_company": "Razorpay",
        "years_experience": 7,
        "city": "Bengaluru",
        "state": "Karnataka",
        "skills": ["python", "fastapi", "postgres", "aws", "kubernetes", "system-design"],
        "looking_for": "Staff/Lead backend at product fintech or B2B SaaS (Bengaluru hybrid)",
        "remote_preference": "any",
        "ctc_min": 3_500_000,
        "ctc_max": 5_000_000,
        "current_ctc": 2_800_000,
        "target_titles": ["Senior Backend Engineer", "Staff Backend Engineer", "Backend Engineer"],
        "path_summary": "Backend IC → staff engineer at high-scale fintech.",
    },
    {
        "user_id": "c2111111-1111-1111-1111-111111111111",
        "candidate_id": "ca211111-1111-1111-1111-111111111111",
        "email": "rahul.candidate@hireschema.com",
        "phone": "+919876543211",
        "full_name": "Rahul Verma",
        "headline": "Frontend engineer · React · TypeScript · design systems",
        "summary": "6 years shipping consumer web apps and trading dashboards at Zerodha.",
        "current_title": "Senior Frontend Engineer",
        "current_company": "Zerodha",
        "years_experience": 6,
        "city": "Bengaluru",
        "state": "Karnataka",
        "skills": ["react", "typescript", "nextjs", "css", "performance", "graphql"],
        "looking_for": "Senior/Lead frontend roles at product companies (React, Next.js)",
        "remote_preference": "any",
        "ctc_min": 2_200_000,
        "ctc_max": 3_200_000,
        "current_ctc": 1_900_000,
        "target_titles": ["Frontend Engineer", "Senior Frontend Engineer", "Full Stack Engineer"],
        "path_summary": "Frontend specialist → lead UI engineer on high-traffic products.",
    },
    {
        "user_id": "c3111111-1111-1111-1111-111111111111",
        "candidate_id": "ca311111-1111-1111-1111-111111111111",
        "email": "ananya.candidate@hireschema.com",
        "phone": "+919876543212",
        "full_name": "Ananya Iyer",
        "headline": "ML engineer · PyTorch · LLMs · MLOps",
        "summary": "5 years productionising ML models for demand forecasting and recommendations.",
        "current_title": "Machine Learning Engineer",
        "current_company": "Swiggy",
        "years_experience": 5,
        "city": "Bengaluru",
        "state": "Karnataka",
        "skills": ["python", "pytorch", "machine-learning", "mlops", "kubernetes", "sql"],
        "looking_for": "Senior ML / AI engineer roles (GenAI, recommendations, MLOps)",
        "remote_preference": "any",
        "ctc_min": 3_000_000,
        "ctc_max": 4_500_000,
        "current_ctc": 2_400_000,
        "target_titles": ["Machine Learning Engineer", "AI Engineer", "Data Scientist"],
        "path_summary": "Applied ML → senior AI engineer on GenAI and production ML systems.",
    },
    {
        "user_id": "c4111111-1111-1111-1111-111111111111",
        "candidate_id": "ca411111-1111-1111-1111-111111111111",
        "email": "vikram.candidate@hireschema.com",
        "phone": "+919876543213",
        "full_name": "Vikram Patel",
        "headline": "Product manager · consumer apps · growth & analytics",
        "summary": "8 years PM experience across fintech and consumer internet in India.",
        "current_title": "Senior Product Manager",
        "current_company": "PhonePe",
        "years_experience": 8,
        "city": "Bengaluru",
        "state": "Karnataka",
        "skills": [
            "product-management",
            "agile",
            "analytics",
            "roadmapping",
            "stakeholder-management",
        ],
        "looking_for": "Senior PM / Group PM roles on consumer or fintech products",
        "remote_preference": "any",
        "ctc_min": 4_000_000,
        "ctc_max": 6_000_000,
        "current_ctc": 3_200_000,
        "target_titles": ["Product Manager", "Senior Product Manager", "Group Product Manager"],
        "path_summary": "Senior PM → group PM owning a major product line.",
    },
    {
        "user_id": "c5111111-1111-1111-1111-111111111111",
        "candidate_id": "ca511111-1111-1111-1111-111111111111",
        "email": "meera.candidate@hireschema.com",
        "phone": "+919876543214",
        "full_name": "Meera Nair",
        "headline": "Growth marketing · paid social · SEO · content",
        "summary": "6 years driving acquisition and retention for Indian consumer apps.",
        "current_title": "Growth Marketing Manager",
        "current_company": "Dunzo",
        "years_experience": 6,
        "city": "Bengaluru",
        "state": "Karnataka",
        "skills": [
            "growth-marketing",
            "seo",
            "google-ads",
            "meta-ads",
            "content-marketing",
            "analytics",
        ],
        "looking_for": "Growth / performance marketing lead roles at Series B+ startups",
        "remote_preference": "any",
        "ctc_min": 2_000_000,
        "ctc_max": 3_500_000,
        "current_ctc": 1_700_000,
        "target_titles": [
            "Growth Marketing Manager",
            "Marketing Manager",
            "Content Marketing Lead",
        ],
        "path_summary": "Growth marketer → head of growth for a scaling consumer brand.",
    },
    {
        "user_id": "c6111111-1111-1111-1111-111111111111",
        "candidate_id": "ca611111-1111-1111-1111-111111111111",
        "email": "karan.candidate@hireschema.com",
        "phone": "+919876543215",
        "full_name": "Karan Singh",
        "headline": "DevOps / SRE · Kubernetes · AWS · Terraform",
        "summary": "7 years running cloud platforms and CI/CD for high-traffic e-commerce.",
        "current_title": "Senior DevOps Engineer",
        "current_company": "Flipkart",
        "years_experience": 7,
        "city": "Bengaluru",
        "state": "Karnataka",
        "skills": ["kubernetes", "aws", "terraform", "linux", "ci-cd", "sre"],
        "looking_for": "Senior DevOps / SRE / platform engineering roles",
        "remote_preference": "any",
        "ctc_min": 2_500_000,
        "ctc_max": 4_000_000,
        "current_ctc": 2_100_000,
        "target_titles": ["DevOps Engineer", "SRE", "Platform Engineer"],
        "path_summary": "DevOps IC → platform engineering lead for cloud-native stacks.",
    },
]

RECRUITERS = [
    {
        "user_id": "b1111111-1111-1111-1111-111111111111",
        "recruiter_id": "b2222222-1111-1111-1111-111111111111",
        "email": "arun.recruiter@hireschema.com",
        "phone": "+919876543220",
        "full_name": "Arun Mehta",
        "company_id": "11111111-1111-1111-1111-111111111111",
        "title": "Talent Lead",
        "bio": "Hiring backend engineers for Acme Fintech.",
        "role_id": "a1111111-1111-1111-1111-111111111111",
        "role_title": "Senior Backend Engineer",
        "jd": """
Senior Backend Engineer — Acme Fintech (Bengaluru, Hybrid)

Scale our payments platform for 50M+ Indians. Own core services in Python/FastAPI,
design for high availability on AWS, and mentor 2-3 engineers.

Must have: 5+ years backend, Python, PostgreSQL, distributed systems.
Nice to have: Fintech, Kubernetes, system design.

Compensation: ₹35-50 LPA. Bengaluru hybrid (3 days office).
""",
        "hiring_brief": "Senior backend engineer for payments infra — Python + Postgres required.",
        "pitch": "Build India-scale payment rails at Acme Fintech — hybrid Bengaluru.",
        "comp_min": 3_500_000,
        "comp_max": 5_000_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "hybrid",
        "must_haves": ["5+ years Python", "PostgreSQL at scale", "Distributed systems", "AWS"],
        "nice_to_haves": ["Fintech experience", "Kubernetes", "System design"],
    },
    {
        "user_id": "b3111111-1111-1111-1111-111111111111",
        "recruiter_id": "b3222222-1111-1111-1111-111111111111",
        "email": "neha.recruiter@hireschema.com",
        "phone": "+919876543221",
        "full_name": "Neha Kapoor",
        "company_id": "d1111111-1111-1111-1111-111111111111",
        "title": "Head of ML Hiring",
        "bio": "Building the AI team at Swiggy AI Lab.",
        "role_id": "a2111111-1111-1111-1111-111111111111",
        "role_title": "Machine Learning Engineer",
        "jd": """
Machine Learning Engineer — Swiggy AI Lab (Bengaluru)

Productionise ML models for recommendations and demand forecasting. Work with Python,
PyTorch, Spark and Kubernetes. Partner with product on experimentation.

Must have: 4+ years ML engineering, Python, PyTorch/TensorFlow, SQL.
Nice to have: MLOps, real-time inference, food-tech domain.

Compensation: ₹28-45 LPA. Bengaluru onsite.
""",
        "hiring_brief": "ML engineer for production models — PyTorch + MLOps.",
        "pitch": "Ship ML that moves millions of orders daily at Swiggy.",
        "comp_min": 2_800_000,
        "comp_max": 4_500_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "onsite",
        "must_haves": ["Python", "PyTorch or TensorFlow", "ML production systems", "SQL"],
        "nice_to_haves": ["MLOps", "Kubernetes", "Spark"],
    },
    {
        "user_id": "b4111111-1111-1111-1111-111111111111",
        "recruiter_id": "b4222222-1111-1111-1111-111111111111",
        "email": "sanjay.recruiter@hireschema.com",
        "phone": "+919876543222",
        "full_name": "Sanjay Reddy",
        "company_id": "d2222222-1111-1111-1111-111111111111",
        "title": "Director of Product",
        "bio": "Hiring PMs for CRED consumer products.",
        "role_id": "a3111111-1111-1111-1111-111111111111",
        "role_title": "Product Manager",
        "jd": """
Product Manager — CRED (Bengaluru)

Own the rewards and engagement product. Define roadmap, run experiments, and work
with engineering and design squads. Strong analytics and stakeholder management.

Must have: 5+ years product management, agile, SQL/analytics tools.
Nice to have: Fintech, consumer apps, growth loops.

Compensation: ₹35-55 LPA. Bengaluru hybrid.
""",
        "hiring_brief": "Senior PM for rewards product — analytics + consumer experience.",
        "pitch": "Shape how millions of Indians earn and redeem rewards on CRED.",
        "comp_min": 3_500_000,
        "comp_max": 5_500_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "hybrid",
        "must_haves": ["5+ years PM", "Agile", "Analytics", "Roadmapping"],
        "nice_to_haves": ["Fintech", "Consumer apps", "A/B testing"],
    },
    {
        "user_id": "b5111111-1111-1111-1111-111111111111",
        "recruiter_id": "b5222222-1111-1111-1111-111111111111",
        "email": "divya.recruiter@hireschema.com",
        "phone": "+919876543223",
        "full_name": "Divya Menon",
        "company_id": "d3333333-1111-1111-1111-111111111111",
        "title": "Growth Hiring Lead",
        "bio": "Hiring growth and marketing talent for Dunzo.",
        "role_id": "a4111111-1111-1111-1111-111111111111",
        "role_title": "Growth Marketing Manager",
        "jd": """
Growth Marketing Manager — Dunzo (Bengaluru)

Own acquisition and retention across paid social, SEO and lifecycle campaigns.
Run experiments, manage budgets, and partner with product on growth loops.

Must have: 4+ years growth/performance marketing, Google Ads, Meta Ads, analytics.
Nice to have: Quick commerce, content marketing, Mixpanel/Amplitude.

Compensation: ₹22-35 LPA. Bengaluru hybrid.
""",
        "hiring_brief": "Growth marketer — paid + SEO + experimentation.",
        "pitch": "Drive growth for India's quick-commerce leader.",
        "comp_min": 2_200_000,
        "comp_max": 3_500_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "hybrid",
        "must_haves": ["Growth marketing", "Google Ads", "Meta Ads", "Analytics"],
        "nice_to_haves": ["SEO", "Content marketing", "A/B testing"],
    },
    {
        "user_id": "b6111111-1111-1111-1111-111111111111",
        "recruiter_id": "b6222222-1111-1111-1111-111111111111",
        "email": "ravi.recruiter@hireschema.com",
        "phone": "+919876543224",
        "full_name": "Ravi Krishnan",
        "company_id": "d4444444-1111-1111-1111-111111111111",
        "title": "Engineering Recruiter",
        "bio": "Hiring full-stack engineers for Postman.",
        "role_id": "a5111111-1111-1111-1111-111111111111",
        "role_title": "Full Stack Engineer",
        "jd": """
Full Stack Engineer — Postman (Remote India)

Build developer-facing features end-to-end in React, TypeScript, Node.js and Go.
Remote-first India team with strong async culture.

Must have: 4+ years full-stack, React, TypeScript, Node.js, REST APIs.
Nice to have: Developer tools, PostgreSQL, distributed systems.

Compensation: ₹20-32 LPA. Fully remote India.
""",
        "hiring_brief": "Full-stack engineer for developer tools — React + Node.",
        "pitch": "Help millions of developers build APIs faster at Postman.",
        "comp_min": 2_000_000,
        "comp_max": 3_200_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "remote",
        "must_haves": ["React", "TypeScript", "Node.js", "4+ years experience"],
        "nice_to_haves": ["Go", "PostgreSQL", "Developer tools"],
    },
]


async def _upsert_auth_user(
    conn: asyncpg.Connection,
    user_id: str,
    email: str,
    password: str,
    full_name: str,
) -> None:
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
        ON CONFLICT (id) DO UPDATE SET
          email = EXCLUDED.email,
          encrypted_password = EXCLUDED.encrypted_password,
          updated_at = NOW()
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


async def _sync_passwords_via_supabase_admin(
    candidates: list[dict],
    recruiters: list[dict],
) -> None:
    """Set passwords via GoTrue Admin API so browser signInWithPassword always works."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        print("WARN: SUPABASE_URL/SERVICE_KEY missing — skipping admin password sync")
        return
    base = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        for c in candidates:
            r = await client.put(
                f"{base}/auth/v1/admin/users/{c['user_id']}",
                headers=headers,
                json={"password": CANDIDATE_PASSWORD, "email_confirm": True},
            )
            if r.status_code >= 400:
                print(f"WARN: password sync failed for {c['email']}: {r.status_code} {r.text[:80]}")
        for r in recruiters:
            resp = await client.put(
                f"{base}/auth/v1/admin/users/{r['user_id']}",
                headers=headers,
                json={"password": RECRUITER_PASSWORD, "email_confirm": True},
            )
            if resp.status_code >= 400:
                print(
                    f"WARN: password sync failed for {r['email']}: {resp.status_code} {resp.text[:80]}"
                )


def _career_profile(title: str, company: str) -> dict:
    """Legacy helper — prefer demo_career_profile() for marketplace candidates."""
    return demo_career_profile(
        {
            "email": "",
            "current_title": title,
            "current_company": company,
            "years_experience": 5,
            "city": "Bengaluru",
            "summary": "",
            "skills": [],
            "target_titles": [],
        }
    )


async def _seed_pipeline_for_role(
    conn: asyncpg.Connection,
    role_id: str,
    role_title: str,
    limit: int = 20,
) -> int:
    job_row = await conn.fetchrow(
        """
        SELECT id FROM public.jobs
        WHERE role_id = $1::uuid AND deleted_at IS NULL AND is_active
        LIMIT 1
        """,
        role_id,
    )
    if not job_row:
        job_row = await conn.fetchrow(
            """
            SELECT j.id FROM public.jobs j
            WHERE j.is_active AND j.deleted_at IS NULL
              AND j.title ILIKE '%' || $1 || '%'
            LIMIT 1
            """,
            role_title[:40],
        )
    if not job_row:
        return 0

    ranked = await rank_candidates_for_job(conn, job_id=job_row["id"], limit=limit)
    count = 0
    for item in ranked:
        cid = item.get("candidate_id")
        if not cid:
            continue
        await conn.execute(
            """
            INSERT INTO public.role_pipeline
              (role_id, candidate_id, stage, match_score, criterion_scores, is_public_search)
            VALUES ($1::uuid, $2::uuid, 'search', $3, $4::jsonb, TRUE)
            ON CONFLICT (role_id, candidate_id) DO UPDATE SET
              match_score = EXCLUDED.match_score,
              criterion_scores = EXCLUDED.criterion_scores,
              is_public_search = TRUE,
              updated_at = NOW()
            """,
            role_id,
            cid,
            item.get("overall_score"),
            json.dumps(item.get("scores", {})),
        )
        count += 1
    return count


async def _deactivate_sample_jobs(conn: asyncpg.Connection) -> int:
    """Hide built-in fake LinkedIn sample jobs so the feed shows live Apify listings."""
    result = await conn.execute(
        """
        UPDATE public.jobs
        SET is_active = FALSE, updated_at = NOW()
        WHERE deleted_at IS NULL
          AND is_active = TRUE
          AND apify_job_id LIKE 'li_3950000%'
        """
    )
    # asyncpg returns "UPDATE N"
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def _ingest_live_jobs(
    conn: asyncpg.Connection,
    settings,
) -> dict:
    """Pull real India jobs via Fantastic.jobs (and LinkedIn when enabled in settings)."""
    use_career_site = settings.apify_enable_career_site_ingest
    use_linkedin = bool(settings.apify_token)
    ingester = JobIngester(
        settings.apify_token,
        conn,
        linkedin_actor=settings.apify_linkedin_jobs_actor,
        career_site_actor=settings.apify_career_site_actor,
        enable_career_site=use_career_site,
    )
    deactivated = await _deactivate_sample_jobs(conn)
    print(f"Deactivated {deactivated} built-in sample jobs")
    stats = await ingester.ingest(
        queries=LIVE_JOB_QUERIES,
        locations=LIVE_JOB_LOCATIONS,
        max_results_per_query=12,
        time_range="7d",
        use_career_site=use_career_site,
        use_linkedin=use_linkedin,
    )
    return stats


async def _cleanup_demo_accounts(conn: asyncpg.Connection, emails: list[str]) -> None:
    """Remove prior demo users and FK-blocking rows (conversations, roles, etc.)."""
    user_ids = await conn.fetch(
        "SELECT id::text FROM auth.users WHERE email = ANY($1::text[])",
        emails,
    )
    if not user_ids:
        return
    ids = [r["id"] for r in user_ids]

    recruiter_ids = await conn.fetch(
        """
        SELECT r.id::text FROM public.recruiters r
        JOIN public.users u ON u.id = r.user_id
        WHERE u.id = ANY($1::uuid[])
        """,
        ids,
    )
    r_ids = [r["id"] for r in recruiter_ids]

    role_ids = (
        await conn.fetch(
            """
        SELECT id::text FROM public.roles
        WHERE recruiter_id = ANY($1::uuid[])
        """,
            r_ids,
        )
        if r_ids
        else []
    )
    role_id_list = [r["id"] for r in role_ids]

    if r_ids:
        await conn.execute(
            """
            DELETE FROM public.messages
            WHERE conversation_id IN (
              SELECT id FROM public.conversations
              WHERE recruiter_id = ANY($1::uuid[])
                 OR role_id = ANY($2::uuid[])
            )
            """,
            r_ids,
            role_id_list or [uuid.UUID(int=0)],
        )
        await conn.execute(
            """
            DELETE FROM public.agent_actions
            WHERE session_id IN (
              SELECT id FROM public.conversations
              WHERE recruiter_id = ANY($1::uuid[])
                 OR role_id = ANY($2::uuid[])
            )
            """,
            r_ids,
            role_id_list or [uuid.UUID(int=0)],
        )
        await conn.execute(
            """
            DELETE FROM public.conversations
            WHERE recruiter_id = ANY($1::uuid[])
               OR role_id = ANY($2::uuid[])
            """,
            r_ids,
            role_id_list or [uuid.UUID(int=0)],
        )

    if role_id_list:
        await conn.execute(
            "DELETE FROM public.role_pipeline WHERE role_id = ANY($1::uuid[])",
            role_id_list,
        )
        await conn.execute(
            "UPDATE public.jobs SET recruiter_id = NULL, role_id = NULL WHERE role_id = ANY($1::uuid[])",
            role_id_list,
        )
        await conn.execute(
            "DELETE FROM public.role_versions WHERE role_id = ANY($1::uuid[])",
            role_id_list,
        )
        await conn.execute("DELETE FROM public.roles WHERE id = ANY($1::uuid[])", role_id_list)

    await conn.execute("DELETE FROM auth.users WHERE id = ANY($1::uuid[])", ids)


async def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to seed: ENVIRONMENT=production", file=sys.stderr)
        raise SystemExit(1)

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    try:
        # Clean prior demo accounts (conversations block recruiter FK cascade)
        await _cleanup_demo_accounts(conn, DEMO_EMAILS)

        # Companies
        for co in COMPANIES:
            await conn.execute(
                """
                INSERT INTO public.companies
                  (id, name, domain, industry, size_bucket, hq_city, hq_state, country_code)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, 'IN')
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  domain = EXCLUDED.domain,
                  industry = EXCLUDED.industry,
                  size_bucket = EXCLUDED.size_bucket,
                  hq_city = EXCLUDED.hq_city,
                  hq_state = EXCLUDED.hq_state,
                  updated_at = NOW()
                """,
                co["id"],
                co["name"],
                co["domain"],
                co["industry"],
                co["size"],
                co["city"],
                co["state"],
            )

        # Live India jobs via Apify (Fantastic.jobs career-site actor + LinkedIn)
        if settings.apify_token:
            print(
                "APIFY_TOKEN set — ingesting live jobs via "
                f"{settings.apify_career_site_actor}"
                + (f" + {settings.apify_linkedin_jobs_actor}" if settings.apify_token else "")
            )
            job_stats = await _ingest_live_jobs(conn, settings)
            print("Live Apify jobs ingested:", job_stats)
        else:
            ingester = JobIngester(apify_token="", db=conn)
            job_stats = await ingester.ingest_sample()
            print("WARN: No APIFY_TOKEN — using built-in sample jobs:", job_stats)

        # Candidates
        for c in CANDIDATES:
            await _upsert_auth_user(
                conn, c["user_id"], c["email"], CANDIDATE_PASSWORD, c["full_name"]
            )
            await conn.execute(
                """
                INSERT INTO public.users (id, email, phone, full_name, role, phone_verified, market, phone_country)
                VALUES ($1::uuid, $2, $3, $4, 'candidate', TRUE, 'IN', 'IN')
                ON CONFLICT (id) DO UPDATE SET
                  email = EXCLUDED.email,
                  phone = EXCLUDED.phone,
                  full_name = EXCLUDED.full_name,
                  phone_verified = TRUE,
                  market = 'IN',
                  phone_country = 'IN',
                  deleted_at = NULL,
                  updated_at = NOW()
                """,
                c["user_id"],
                c["email"],
                c["phone"],
                c["full_name"],
            )

            ctx = demo_candidate_context(c)
            career_profile = ctx["career_profile"]
            career_intel = demo_career_intelligence_blob(c)
            parsed_resume = demo_parsed_resume(c)

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
                  $7, $8, $9, 30,
                  $10, $11, $12, $13::text[],
                  $14, $15, TRUE,
                  $16::jsonb, $17::jsonb, NOW()
                )
                ON CONFLICT (user_id) DO UPDATE SET
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  current_title = EXCLUDED.current_title,
                  current_company = EXCLUDED.current_company,
                  location_city = EXCLUDED.location_city,
                  location_state = EXCLUDED.location_state,
                  years_experience = EXCLUDED.years_experience,
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
                c["candidate_id"],
                c["user_id"],
                c["headline"],
                c["summary"],
                c["current_title"],
                c["current_company"],
                c["city"],
                c["state"],
                c["years_experience"],
                c["ctc_min"],
                c["ctc_max"],
                c["current_ctc"],
                c["skills"],
                c["looking_for"],
                c["remote_preference"],
                json.dumps(career_profile),
                json.dumps(career_intel),
            )

            await conn.execute(
                """
                DELETE FROM public.resumes
                WHERE candidate_id = $1::uuid AND file_path LIKE 'resumes/demo/%'
                """,
                c["candidate_id"],
            )
            await conn.execute(
                """
                INSERT INTO public.resumes
                  (id, candidate_id, file_path, file_name, is_primary, raw_text, parsed_data)
                VALUES ($1::uuid, $2::uuid, $3, $4, TRUE, $5, $6::jsonb)
                """,
                str(uuid.uuid4()),
                c["candidate_id"],
                f"resumes/demo/{c['email']}.pdf",
                f"{c['full_name']}_resume.pdf",
                f"{c['summary']} Skills: {', '.join(c['skills'])}",
                json.dumps(parsed_resume),
            )

            await conn.execute(
                """
                INSERT INTO public.career_paths
                  (id, candidate_id, summary, steps, target_titles, target_locations, model)
                VALUES ($1::uuid, $2::uuid, $3, '[]'::jsonb, $4::text[], $5::text[], 'seed')
                """,
                str(uuid.uuid4()),
                c["candidate_id"],
                f"{c['current_title']}: {c['path_summary']}",
                c["target_titles"],
                [c["city"]],
            )

        # Recruiters + roles → jobs feed
        for r in RECRUITERS:
            await _upsert_auth_user(
                conn, r["user_id"], r["email"], RECRUITER_PASSWORD, r["full_name"]
            )
            await conn.execute(
                """
                INSERT INTO public.users (id, email, phone, full_name, role, phone_verified, market, phone_country)
                VALUES ($1::uuid, $2, $3, $4, 'recruiter', TRUE, 'IN', 'IN')
                ON CONFLICT (id) DO UPDATE SET
                  email = EXCLUDED.email,
                  phone = EXCLUDED.phone,
                  full_name = EXCLUDED.full_name,
                  phone_verified = TRUE,
                  market = 'IN',
                  phone_country = 'IN',
                  deleted_at = NULL,
                  updated_at = NOW()
                """,
                r["user_id"],
                r["email"],
                r["phone"],
                r["full_name"],
            )
            await conn.execute(
                """
                INSERT INTO public.recruiters (id, user_id, company_id, title, bio)
                VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                  company_id = EXCLUDED.company_id,
                  title = EXCLUDED.title,
                  bio = EXCLUDED.bio,
                  deleted_at = NULL,
                  updated_at = NOW()
                """,
                r["recruiter_id"],
                r["user_id"],
                r["company_id"],
                r["title"],
                r["bio"],
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
                  $1::uuid, $2::uuid, $3::uuid, $4, $5, 'hiring',
                  $6, $7, $8, $9,
                  $10, $11, $12,
                  $13::jsonb, $14::jsonb, $15::jsonb
                )
                ON CONFLICT (id) DO UPDATE SET
                  title = EXCLUDED.title,
                  jd_text = EXCLUDED.jd_text,
                  status = EXCLUDED.status,
                  hiring_brief = EXCLUDED.hiring_brief,
                  candidate_pitch = EXCLUDED.candidate_pitch,
                  comp_min = EXCLUDED.comp_min,
                  comp_max = EXCLUDED.comp_max,
                  location_city = EXCLUDED.location_city,
                  location_state = EXCLUDED.location_state,
                  remote_policy = EXCLUDED.remote_policy,
                  must_haves = EXCLUDED.must_haves,
                  nice_to_haves = EXCLUDED.nice_to_haves,
                  updated_at = NOW()
                """,
                r["role_id"],
                r["company_id"],
                r["recruiter_id"],
                r["role_title"],
                r["jd"].strip(),
                r["hiring_brief"],
                r["pitch"],
                r["comp_min"],
                r["comp_max"],
                r["city"],
                r["state"],
                r["remote_policy"],
                json.dumps(r["must_haves"]),
                json.dumps(r["nice_to_haves"]),
                json.dumps({"seniority": "mid-senior", "source": "seed"}),
            )

            await conn.execute(
                """
                INSERT INTO public.conversations (id, recruiter_id, role_id, agent, title)
                SELECT gen_random_uuid(), $2::uuid, $1::uuid, 'nitya', $3
                WHERE NOT EXISTS (
                  SELECT 1 FROM public.conversations
                  WHERE role_id = $1::uuid
                    AND agent = 'nitya'
                    AND deleted_at IS NULL
                )
                """,
                r["role_id"],
                r["recruiter_id"],
                f"Intake: {r['role_title']}",
            )

            pub = await publish_role_to_jobs(
                conn,
                role_id=r["role_id"],
                recruiter_id=r["recruiter_id"],
            )
            print(f"Published role {r['role_title']}: {pub}")

        # Match scores — demo candidates only (faster than full recompute_all)
        engine = MatchingEngine(conn)
        total_pairs = 0
        for c in CANDIDATES:
            scored = await engine.score_candidate(c["candidate_id"], limit=40)
            total_pairs += scored
        match_stats = {"candidates_scored": len(CANDIDATES), "total_pairs_scored": total_pairs}
        print("Match scoring:", match_stats)

        # Recruiter pipelines (search results pre-populated)
        pipeline_total = 0
        for r in RECRUITERS:
            n = await _seed_pipeline_for_role(conn, r["role_id"], r["role_title"])
            pipeline_total += n
            print(f"Pipeline for {r['role_title']}: {n} candidates")

        await _sync_passwords_via_supabase_admin(CANDIDATES, RECRUITERS)

        # Ensure users.role matches recruiters rows (bootstrap tab mismatch guard)
        await conn.execute(
            """
            UPDATE public.users u
            SET role = 'recruiter', updated_at = NOW()
            FROM public.recruiters r
            WHERE r.user_id = u.id
              AND r.deleted_at IS NULL
              AND u.deleted_at IS NULL
              AND u.role <> 'recruiter'
            """
        )

        job_count = await conn.fetchval(
            """
            SELECT count(*) FROM public.jobs
            WHERE is_active AND deleted_at IS NULL
              AND expires_at > NOW()
            """
        )
        score_count = await conn.fetchval("SELECT count(*) FROM public.match_scores")

        print("\n" + "=" * 60)
        print("Marketplace demo seeded successfully")
        print("=" * 60)
        print(f"Active jobs in feed: {job_count}")
        print(f"Match score rows:    {score_count}")
        print(f"Pipeline rows:       {pipeline_total}")
        print("\nEnable dev login: NEXT_PUBLIC_DEV_EMAIL_LOGIN=true\n")
        print("Candidates (password: DemoCandidate26!):")
        for c in CANDIDATES:
            print(f"  {c['email']} — {c['current_title']} · {c['looking_for'][:50]}...")
        print("\nRecruiters (password: DemoRecruiter26!):")
        for r in RECRUITERS:
            print(f"  {r['email']} — hiring {r['role_title']} at role {r['role_id'][:8]}...")
        print("\nSign in: http://localhost:3001/signup?mode=signin")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
