"""
Backfill rich demo candidate profiles (experience, education, career intelligence).

DEV/STAGING ONLY.

Usage (from api/):
    .venv/bin/python scripts/backfill_demo_candidate_profiles.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.demo_candidate_fixtures import (
    demo_candidate_context,
    demo_career_intelligence_blob,
    demo_parsed_resume,
)

DEMO_EMAILS = [
    "priya.candidate@hireschema.com",
    "rahul.candidate@hireschema.com",
    "ananya.candidate@hireschema.com",
    "vikram.candidate@hireschema.com",
    "meera.candidate@hireschema.com",
    "karan.candidate@hireschema.com",
]


async def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing: ENVIRONMENT=production", file=sys.stderr)
        raise SystemExit(1)

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)

    rows = await conn.fetch(
        """
        SELECT c.id::text AS candidate_id, u.email, u.full_name,
               c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city AS city, c.location_state AS state,
               c.skills, c.expected_ctc_min AS ctc_min, c.expected_ctc_max AS ctc_max,
               c.current_ctc, c.looking_for, c.remote_preference
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE u.email = ANY($1::text[])
          AND c.deleted_at IS NULL
        """,
        DEMO_EMAILS,
    )

    for row in rows:
        c = dict(row)
        c["email"] = str(c["email"]).lower()
        path_row = await conn.fetchrow(
            "SELECT target_titles FROM public.career_paths WHERE candidate_id = $1::uuid ORDER BY created_at DESC LIMIT 1",
            c["candidate_id"],
        )
        c["target_titles"] = list(path_row["target_titles"] or []) if path_row else []
        ctx = demo_candidate_context(c)
        career_profile = ctx["career_profile"]
        career_intel = demo_career_intelligence_blob(c)
        parsed = demo_parsed_resume(c)

        await conn.execute(
            """
            UPDATE public.candidates SET
              career_profile = $2::jsonb,
              career_intelligence = $3::jsonb,
              career_intelligence_updated_at = NOW(),
              profile_complete = TRUE,
              updated_at = NOW()
            WHERE id = $1::uuid
            """,
            c["candidate_id"],
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
            f"{c.get('summary') or ''} Skills: {', '.join(c.get('skills') or [])}",
            json.dumps(parsed),
        )
        print(f"Updated {c['email']}")

    await conn.close()
    print(f"Backfilled {len(rows)} demo candidates")


if __name__ == "__main__":
    asyncio.run(main())
