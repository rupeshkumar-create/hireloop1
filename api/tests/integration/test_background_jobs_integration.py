"""Integration: background_jobs enqueue + process against real Postgres."""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import pytest
from httpx import AsyncClient

from hireloop_api.config import Settings
from hireloop_api.services import background_jobs as bj
from hireloop_api.services.background_jobs import (
    AARYA_AUTO_INGEST,
    claim_next_job,
    enqueue_job,
    process_job,
)


@pytest.mark.asyncio
async def test_enqueue_claim_and_complete(db_conn: asyncpg.Connection) -> None:
    job_id = await enqueue_job(
        db_conn,
        kind=AARYA_AUTO_INGEST,
        payload={"candidate_id": str(uuid.uuid4())},
        idempotency_key=f"test-{uuid.uuid4().hex}",
    )

    claimed = await claim_next_job(db_conn, worker_id="integration")
    assert claimed is not None
    assert claimed["id"] == str(job_id)

    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    ran: dict[str, Any] = {}

    async def _noop(_settings: Settings, payload: dict[str, Any]) -> None:
        ran["candidate_id"] = payload["candidate_id"]

    original = bj._HANDLERS[AARYA_AUTO_INGEST]
    bj._HANDLERS[AARYA_AUTO_INGEST] = _noop
    try:
        await process_job(db_conn, settings, claimed)
    finally:
        bj._HANDLERS[AARYA_AUTO_INGEST] = original

    status = await db_conn.fetchval(
        "SELECT status FROM public.background_jobs WHERE id = $1::uuid",
        job_id,
    )
    assert status == "completed"
    assert "candidate_id" in ran


@pytest.mark.asyncio
async def test_find_jobs_enqueues_career_ingest(
    api_client: AsyncClient,
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    path_id = uuid.uuid4()
    await db_conn.execute(
        """
        INSERT INTO public.career_paths
          (id, candidate_id, current_role, summary, steps, target_titles,
           target_locations, model, prioritized_title)
        VALUES (
          $1, $2::uuid, 'Engineer', 'Growing', '[]'::jsonb,
          $3::text[], $4::text[], 'test', $5
        )
        """,
        path_id,
        uuid.UUID(candidate_user["candidate_id"]),
        ["Senior Engineer"],
        ["Bengaluru"],
        "Senior Engineer",
    )

    res = await api_client.post("/api/v1/career/path/find-jobs")
    assert res.status_code == 200

    row = await db_conn.fetchrow(
        """
        SELECT kind, status FROM public.background_jobs
        WHERE payload->>'candidate_id' = $1
        ORDER BY created_at DESC LIMIT 1
        """,
        candidate_user["candidate_id"],
    )
    assert row is not None
    assert row["kind"] == "career_path_ingest"
    assert row["status"] in ("pending", "running", "completed")
