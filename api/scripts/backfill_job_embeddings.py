"""
Backfill job embeddings (HIR-55).

Finds active India jobs with no jd_embedding and generates their 3 vectors via
EmbeddingService, in batches. Idempotent — safe to re-run; only touches jobs that
are still missing embeddings.

    cd api && uv run python scripts/backfill_job_embeddings.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

import asyncpg

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from hireloop_api.services.embeddings import EmbeddingService  # noqa: E402


def _dsn() -> str:
    raw = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    pwd = re.match(r"postgresql://([^:]+):([^@]+)@", raw).group(2)
    return (
        f"postgresql://postgres.blwudfxurykzyutkqkoi:{pwd}"
        "@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
    )


async def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set")

    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT j.id
            FROM public.jobs j
            WHERE j.is_active AND j.deleted_at IS NULL AND j.country_code = 'IN'
              AND NOT EXISTS (
                SELECT 1 FROM public.job_embeddings je
                WHERE je.job_id = j.id AND je.jd_embedding IS NOT NULL
              )
            """
        )
        ids = [str(r["id"]) for r in rows]
        print(f"jobs missing embeddings: {len(ids)}", flush=True)

        svc = EmbeddingService(api_key, conn)
        done = 0
        # Batch in chunks; embed_jobs_batch already parallelises within a chunk.
        for i in range(0, len(ids), 40):
            chunk = ids[i : i + 40]
            res = await svc.embed_jobs_batch(chunk)
            done += sum(1 for ok in res.values() if ok)
            print(f"  {done}/{len(ids)} embedded", flush=True)

        print(f"BACKFILL_DONE embedded={done} of {len(ids)}", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
