"""
Backfill JD enrichment (backend plan #30).

Finds active jobs that have a description but no structured skills (typically ATS
feeds) and runs one LLM pass to fill skills_required, and seniority/CTC when
they're missing. Only fills empty fields — never overwrites curated data.

Run:  cd api && uv run python scripts/enrich_jobs.py [--limit N]
Cron: after ingest_ats.py, before recompute_matches.py.
"""

from __future__ import annotations

import asyncio
import json
import sys

import asyncpg

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db_pool
from hireloop_api.services.jd_enrichment import enrich_job_description

CONCURRENCY = 4


async def _enrich_one(
    sem: asyncio.Semaphore, pool: asyncpg.Pool, job: asyncpg.Record, settings: Settings
) -> bool:
    async with sem:
        data = await enrich_job_description(job["title"], job["description"] or "", settings)
    if not data or not data["skills_required"]:
        return False
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE public.jobs SET
                skills_required = $2,
                seniority = COALESCE(seniority, $3),
                ctc_min = COALESCE(ctc_min, $4),
                ctc_max = COALESCE(ctc_max, $5),
                raw_data = COALESCE(raw_data, '{}'::jsonb) || $6::jsonb,
                updated_at = NOW()
            WHERE id = $1
            """,
            job["id"],
            data["skills_required"],
            data["seniority"],
            data["ctc_min"],
            data["ctc_max"],
            json.dumps({"jd_enriched": True}),
        )
    return True


async def main() -> None:
    limit = 100
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (ValueError, IndexError):
            pass

    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY not set — JD enrichment needs an LLM.")
        return

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        jobs = await conn.fetch(
            """
            SELECT id, title, description FROM public.jobs
            WHERE is_active = TRUE AND deleted_at IS NULL
              AND description IS NOT NULL AND length(description) > 80
              AND (skills_required IS NULL OR array_length(skills_required, 1) IS NULL)
            ORDER BY scraped_at DESC NULLS LAST
            LIMIT $1
            """,
            limit,
        )
    print(f"Enriching {len(jobs)} jobs missing structured skills…")
    if not jobs:
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*(_enrich_one(sem, pool, j, settings) for j in jobs))
    print(f"Done: enriched {sum(results)}/{len(jobs)}.")


if __name__ == "__main__":
    asyncio.run(main())
