"""
Seed two published recruiter roles + jobs aligned to the test resumes:

  Profile (4).pdf → Vivek Kumar (gerihaj150@kinws.com) — Target category / apparel
  Profile (1).pdf → Rupesh Kumar (youthinkso@live.in) — Candidately GTM / staffing SaaS

Recruiter posting the roles: rupesh.kumar@candidate.ly

Run from api/:
    .venv/bin/python scripts/seed_rupesh_test_jobs.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.embeddings import EmbeddingService
from hireloop_api.services.intro_service import publish_role_to_jobs
from hireloop_api.services.matching import MatchingEngine
from hireloop_api.services.profile_experience import (
    build_merged_experience,
    reconcile_candidate_overview,
)

RECRUITER_EMAIL = "rupesh.kumar@candidate.ly"
COMPANY_ID = uuid.UUID("e1000001-0000-4000-8000-000000000001")
ROLE_CATEGORY_ID = uuid.UUID("e1000002-0000-4000-8000-000000000002")
ROLE_GTM_ID = uuid.UUID("e1000003-0000-4000-8000-000000000003")

# Resume owners (Profile 4 / Profile 1 in Downloads)
CANDIDATE_VIVEK_EMAIL = "gerihaj150@kinws.com"
CANDIDATE_RUPESH_EMAIL = "youthinkso@live.in"
RESUME_VIVEK_FILE = "Profile (4).pdf"
RESUME_RUPESH_FILE = "Profile (1).pdf"

# ── Derived from parsed Profile (4).pdf — Vivek Kumar ───────────────────────
ROLES = [
    {
        "id": ROLE_CATEGORY_ID,
        "title": "Category Planner — Apparel & Fashion",
        "hiring_brief": "Category planner for apparel — OTB, fashion buying, private label.",
        "pitch": "Mirror a Target-style planning role for India's leading apparel retailer.",
        "comp_min": 2_000_000,
        "comp_max": 3_200_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "hybrid",
        "must_haves": [
            "category planning",
            "category management",
            "fashion buying",
            "merchandising",
            "apparel",
            "garment manufacturing",
            "fashion merchandising",
            "private label",
            "retail buying",
            "category analysis",
            "e-commerce",
        ],
        "nice_to_haves": [
            "Target",
            "Myntra",
            "Bewakoof",
            "OTB planning",
            "Assortment planning",
        ],
        "jd": """
Category Planner — Apparel & Fashion (Bengaluru, hybrid)

We're hiring a Category Planner to own apparel assortment, in-season margin, and vendor
partnerships for a national retailer — a role comparable to Category Planner / Senior
Category Analyst tracks at Target, Myntra, or Bewakoof.

What you'll do:
- Lead category planning and analysis for apparel (OTB, assortment, in-season pivots)
- Drive fashion buying and merchandising with private-label and national brands
- Partner with garment manufacturing vendors on cost, quality, and speed
- Use data for category analysis across e-commerce and store channels

Must have (from our ideal profile):
- Current or recent Category Planner / Senior Category Analyst experience in apparel
- Strong fashion buying, merchandising, and garment manufacturing exposure
- Retail buying + category management in fashion / D2C (Myntra, Bewakoof-style a plus)
- Private label development and category analysis at scale

Nice to have:
- Big-box or multi-channel apparel retail planning cadence
- E-commerce fashion merchandising background

Compensation: ₹20–32 LPA. Bengaluru hybrid (3 days office).
""",
        "match_email": CANDIDATE_VIVEK_EMAIL,
        "resume_file": RESUME_VIVEK_FILE,
    },
    {
        "id": ROLE_GTM_ID,
        "title": "Go-To-Market Lead — AI Resume Builder (Staffing SaaS)",
        "hiring_brief": "GTM lead for an AI resume builder sold to staffing agencies.",
        "pitch": "Own GTM for a Candidately-style AI resume + recruiter workflow product.",
        "comp_min": 2_800_000,
        "comp_max": 4_500_000,
        "city": "Bengaluru",
        "state": "Karnataka",
        "remote_policy": "flex",
        "must_haves": [
            "go-to-market strategy",
            "sales operations",
            "ai resume builder",
            "staffing industry",
            "bullhorn",
            "product demos",
            "recruiter enablement",
            "inside sales",
            "business development",
            "customer adoption",
            "onboarding",
            "sales development",
            "marketing",
            "digital strategy",
            "automation",
            "artificial intelligence (ai)",
        ],
        "nice_to_haves": [
            "Candidately",
            "HR-tech SaaS",
            "World Staffing Summit",
            "EasyEcom",
            "HubSpot",
        ],
        "jd": """
Go-To-Market Lead — AI Resume Builder (Staffing / HR-tech SaaS)

We're building an AI-native resume builder and recruiter workflow platform for staffing
agencies (think Candidately × Bullhorn ecosystem). We need a GTM Lead who has already
run sales ops + GTM in this exact category.

What you'll do:
- Own go-to-market strategy: ICP, positioning, pipeline, and revenue motion
- Run product demos and recruiter enablement for staffing agency buyers
- Build sales operations, onboarding playbooks, and customer adoption programs
- Partner with product on AI resume builder features staffing recruiters actually use

Must have:
- Go-To-Market Lead or Sales Operations Manager experience in staffing / HR-tech SaaS
- Hands-on with AI resume builder or similar recruiter-facing AI products
- Bullhorn or staffing-industry CRM/workflows; inside sales & business development
- Product demos, client engagement, event-led demand (staffing summits a plus)
- Marketing + digital strategy with automation for outbound and nurture

Background we love:
- Candidately, Gustav-style sales development, or e-commerce B2B sales (EasyEcom)
- Artificial intelligence (AI) product GTM — not generic enterprise SaaS only

Compensation: ₹28–45 LPA. India remote-flex with quarterly Bengaluru sync.
""",
        "match_email": CANDIDATE_RUPESH_EMAIL,
        "resume_file": RESUME_RUPESH_FILE,
    },
]


async def _ensure_company_and_recruiter(conn: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID]:
    row = await conn.fetchrow(
        """
        SELECT u.id AS user_id, r.id AS recruiter_id, r.company_id
        FROM public.users u
        JOIN public.recruiters r ON r.user_id = u.id AND r.deleted_at IS NULL
        WHERE u.email = $1 AND u.deleted_at IS NULL
        """,
        RECRUITER_EMAIL,
    )
    if not row:
        raise SystemExit(f"Recruiter not found for {RECRUITER_EMAIL}")

    await conn.execute(
        """
        INSERT INTO public.companies
          (id, name, domain, industry, size_bucket, hq_city, hq_state, country_code)
        VALUES ($1, 'Hireloop Test Co', 'hireloop-test.in', 'Hiring Tech', '11-50',
                'Bengaluru', 'Karnataka', 'IN')
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW()
        """,
        COMPANY_ID,
    )

    recruiter_id = row["recruiter_id"]
    if row["company_id"] != COMPANY_ID:
        await conn.execute(
            """
            UPDATE public.recruiters
            SET company_id = $2, title = COALESCE(title, 'Talent Lead'), updated_at = NOW()
            WHERE id = $1
            """,
            recruiter_id,
            COMPANY_ID,
        )

    return row["user_id"], recruiter_id


async def _sync_candidate_from_resume(
    conn: asyncpg.Connection,
    *,
    email: str,
    resume_file: str,
) -> str | None:
    """Refresh candidate overview + skills from the primary resume parse."""
    row = await conn.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.looking_for, c.skills, c.linkedin_data, c.career_profile,
               r.parsed_data
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        JOIN public.resumes r ON r.candidate_id = c.id AND r.file_name = $2
        WHERE u.email = $1 AND c.deleted_at IS NULL
        ORDER BY r.is_primary DESC, r.version DESC
        LIMIT 1
        """,
        email,
        resume_file,
    )
    if not row:
        print(f"  WARN: no resume {resume_file} for {email}")
        return None

    parsed = row["parsed_data"]
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    if not isinstance(parsed, dict):
        return str(row["id"])

    cand = dict(row)
    skills = [str(s) for s in (parsed.get("skills") or cand.get("skills") or []) if str(s).strip()]
    cand["skills"] = skills
    if parsed.get("current_title"):
        cand["current_title"] = parsed["current_title"]
    if parsed.get("current_company"):
        cand["current_company"] = parsed["current_company"]
    if parsed.get("headline"):
        cand["headline"] = parsed["headline"]
    if parsed.get("summary"):
        cand["summary"] = parsed["summary"]
    if parsed.get("years_experience"):
        cand["years_experience"] = parsed["years_experience"]

    experience = build_merged_experience(
        resume_experience=[e for e in (parsed.get("work_experience") or []) if isinstance(e, dict)],
        linkedin_data=cand.get("linkedin_data"),
        career_profile=cand.get("career_profile")
        if isinstance(cand.get("career_profile"), dict)
        else None,
        career_intelligence=None,
        candidate=cand,
        skills=skills,
    )
    reconciled, fixes = reconcile_candidate_overview(
        cand, experience, linkedin_data=cand.get("linkedin_data")
    )

    set_parts = ["skills = $2::text[]", "profile_complete = TRUE", "updated_at = NOW()"]
    values: list[object] = [row["id"], skills]
    idx = 3
    for field in (
        "headline",
        "summary",
        "current_title",
        "current_company",
        "years_experience",
        "looking_for",
    ):
        if field in reconciled and reconciled[field] is not None:
            set_parts.append(f"{field} = ${idx}")
            values.append(reconciled[field])
            idx += 1

    await conn.execute(
        f"UPDATE public.candidates SET {', '.join(set_parts)} WHERE id = $1::uuid",
        *values,
    )
    print(f"  synced {email} from {resume_file} ({len(fixes)} overview fixes)")
    return str(row["id"])


async def _upsert_role(conn: asyncpg.Connection, recruiter_id: uuid.UUID, spec: dict) -> None:
    await conn.execute(
        """
        INSERT INTO public.roles (
          id, company_id, recruiter_id, title, jd_text, status,
          hiring_brief, candidate_pitch, comp_min, comp_max,
          location_city, location_state, remote_policy,
          must_haves, nice_to_haves, jd_structured
        )
        VALUES (
          $1, $2, $3, $4, $5, 'hiring',
          $6, $7, $8, $9,
          $10, $11, $12,
          $13::jsonb, $14::jsonb, $15::jsonb
        )
        ON CONFLICT (id) DO UPDATE SET
          title = EXCLUDED.title,
          jd_text = EXCLUDED.jd_text,
          status = 'hiring',
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
        spec["id"],
        COMPANY_ID,
        recruiter_id,
        spec["title"],
        spec["jd"].strip(),
        spec["hiring_brief"],
        spec["pitch"],
        spec["comp_min"],
        spec["comp_max"],
        spec["city"],
        spec["state"],
        spec["remote_policy"],
        json.dumps(spec["must_haves"]),
        json.dumps(spec["nice_to_haves"]),
        json.dumps({"seniority": "senior", "source": "seed_rupesh_test_jobs"}),
    )

    await conn.execute(
        """
        INSERT INTO public.conversations (id, recruiter_id, role_id, agent, title)
        SELECT gen_random_uuid(), $2, $1, 'nitya', $3
        WHERE NOT EXISTS (
          SELECT 1 FROM public.conversations
          WHERE role_id = $1 AND agent = 'nitya' AND deleted_at IS NULL
        )
        """,
        spec["id"],
        recruiter_id,
        f"Intake: {spec['title']}",
    )


async def _candidate_id(conn: asyncpg.Connection, email: str) -> str | None:
    val = await conn.fetchval(
        """
        SELECT c.id::text FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE u.email = $1 AND c.deleted_at IS NULL
        """,
        email,
    )
    return str(val) if val else None


async def _print_score_matrix(
    conn: asyncpg.Connection,
    job_ids: list[tuple[str, str]],
    candidates: list[tuple[str, str]],
) -> None:
    print("\nMatch matrix (resume ↔ job):")
    for cand_email, label in candidates:
        cid = await _candidate_id(conn, cand_email)
        if not cid:
            continue
        for title, job_id in job_ids:
            row = await conn.fetchrow(
                """
                SELECT ms.overall_score, ms.skills_score
                FROM public.match_scores ms
                WHERE ms.candidate_id = $1::uuid AND ms.job_id = $2::uuid
                """,
                uuid.UUID(cid),
                uuid.UUID(job_id),
            )
            if row:
                print(
                    f"  {label} × {title[:40]:40} "
                    f"overall={row['overall_score']:.2f} skills={row['skills_score']:.2f}"
                )


async def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        _user_id, recruiter_id = await _ensure_company_and_recruiter(conn)
        print(f"Recruiter {RECRUITER_EMAIL} → {recruiter_id}\n")

        print("Syncing candidates from resumes…")
        for spec in ROLES:
            await _sync_candidate_from_resume(
                conn,
                email=spec["match_email"],
                resume_file=spec["resume_file"],
            )

        job_ids: list[tuple[str, str]] = []
        for spec in ROLES:
            await _upsert_role(conn, recruiter_id, spec)
            pub = await publish_role_to_jobs(
                conn,
                role_id=str(spec["id"]),
                recruiter_id=str(recruiter_id),
            )
            job_id = pub.get("job_id")
            if not job_id:
                print(f"WARN: failed to publish {spec['title']}: {pub}")
                continue
            job_ids.append((spec["title"], job_id))
            print(f"✓ Published: {spec['title']}")

        embedder = EmbeddingService(settings.openrouter_api_key or "", conn)
        engine = MatchingEngine(conn)

        for _title, job_id in job_ids:
            await embedder.embed_job(job_id)
            await engine.score_job(job_id, notify=False)

        await _print_score_matrix(
            conn,
            job_ids,
            [
                (CANDIDATE_VIVEK_EMAIL, "Profile (4) Vivek"),
                (CANDIDATE_RUPESH_EMAIL, "Profile (1) Rupesh"),
            ],
        )

        print("\nDone — recruiter:", RECRUITER_EMAIL)
        print("Resumes: Profile (4).pdf → Category role | Profile (1).pdf → GTM role")

        from hireloop_api.services.test_jobs import ensure_test_match_scores

        candidate_ids = await conn.fetch(
            "SELECT id::text FROM public.candidates WHERE deleted_at IS NULL"
        )
        for row in candidate_ids:
            await ensure_test_match_scores(
                conn,
                row["id"],
                market="IN",
                remote_preference="any",
            )
        print(f"Ensured test match scores for {len(candidate_ids)} candidates")
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
