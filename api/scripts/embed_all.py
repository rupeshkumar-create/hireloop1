"""
Generate embeddings for all pending jobs + candidates — the semantic ("best
precision") layer of matching.

Once `OPENROUTER_API_KEY` is set, this populates `job_embeddings` and
`candidate_embeddings` (text-embedding-3-small via OpenRouter). `score_pair`
then blends pgvector cosine similarity with the lexical signals — which is what
cleanly separates, e.g., a UX designer from a "Sales Manager" role even when a
stray skill keyword overlaps.

Operational order for a fresh, relevant feed:
    1. uv run python scripts/run_ingest.py --candidate you@example.com   # career-path jobs
    2. uv run python scripts/embed_all.py                                # semantic layer
    3. uv run python scripts/recompute_matches.py                        # re-score

Run from the api/ directory.
"""

from __future__ import annotations

import asyncio

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.embeddings import EmbeddingService


async def main() -> None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise SystemExit(
            "OPENROUTER_API_KEY is not set in api/.env — needed for the embeddings layer."
        )
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set in api/.env")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        svc = EmbeddingService(api_key=settings.openrouter_api_key, db=conn)
        j_ok, j_fail = await svc.embed_all_pending_jobs()
        c_ok, c_fail = await svc.embed_all_pending_candidates()
        print("✅ Embeddings generated:")
        print(f"   jobs:       {j_ok} ok, {j_fail} failed")
        print(f"   candidates: {c_ok} ok, {c_fail} failed")
        print("\nNext: uv run python scripts/recompute_matches.py")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
