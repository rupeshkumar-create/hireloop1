"""Integration: sample job ingest → DB rows (no Apify network)."""

from __future__ import annotations

import asyncpg
import pytest

from hireloop_api.services.apify.job_ingester import JobIngester


@pytest.mark.asyncio
async def test_sample_ingest_inserts_india_jobs(db_conn: asyncpg.Connection) -> None:
    ingester = JobIngester(apify_token="", db=db_conn)
    stats = await ingester.ingest_sample()
    assert stats["inserted"] + stats["updated"] >= 1

    count = await db_conn.fetchval(
        """
        SELECT COUNT(*) FROM public.jobs
        WHERE country_code = 'IN' AND deleted_at IS NULL AND is_active = TRUE
        """
    )
    assert int(count or 0) >= 1
