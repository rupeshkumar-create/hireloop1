"""Integration: background_jobs enqueue + process against real Postgres."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import asyncpg
import pytest
from httpx import AsyncClient

from hireloop_api.config import Settings
from hireloop_api.services import background_jobs as bj
from hireloop_api.services.ai_operations import enqueue_ai_operation
from hireloop_api.services.background_jobs import (
    AARYA_AUTO_INGEST,
    HandlerResult,
    claim_next_job,
    enqueue_job,
    process_job,
)
from tests.pool_shim import ConnectionPoolShim


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
        await process_job(ConnectionPoolShim(db_conn), settings, claimed)
    finally:
        bj._HANDLERS[AARYA_AUTO_INGEST] = original

    status = await db_conn.fetchval(
        "SELECT status FROM public.background_jobs WHERE id = $1::uuid",
        job_id,
    )
    assert status == "completed"
    assert "candidate_id" in ran


@pytest.mark.asyncio
async def test_find_jobs_enqueues_pool_ingest_for_senior_path(
    api_client: AsyncClient,
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    """Senior paths with a canonical pool definition enqueue pool_ingest, not per-candidate Apify."""
    path_id = uuid.uuid4()
    await db_conn.execute(
        """
        INSERT INTO public.career_paths
          (id, candidate_id, "current_role", summary, steps, target_titles,
           target_locations, model, prioritized_title)
        VALUES (
          $1, $2::uuid, 'Growth Lead', 'Growing', '[]'::jsonb,
          $3::text[], $4::text[], 'test', $5
        )
        """,
        path_id,
        uuid.UUID(candidate_user["candidate_id"]),
        ["Head of Growth"],
        ["Bengaluru"],
        "Head of Growth",
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
    assert row["kind"] == "pool_ingest"
    assert row["status"] in ("pending", "running", "completed")


async def _insert_linked_running_job(
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
    *,
    kind: str,
    attempts: int = 1,
    max_attempts: int = 3,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, Any]]:
    operation_id = uuid.uuid4()
    job_id = uuid.uuid4()
    await db_conn.execute(
        """
        INSERT INTO public.background_jobs
          (id, kind, payload, idempotency_key, status, attempts, max_attempts, started_at)
        VALUES
          ($1, $2, jsonb_build_object('operation_id', $3::text), $4,
           'running', $5, $6, NOW())
        """,
        job_id,
        kind,
        operation_id,
        f"worker-operation:{operation_id}",
        attempts,
        max_attempts,
    )
    await db_conn.execute(
        """
        INSERT INTO public.ai_operations
          (id, user_id, candidate_id, kind, background_job_id, idempotency_key,
           status, stage, message)
        VALUES ($1, $2::uuid, $3::uuid, $4, $5, $6, 'queued', 'queued', 'Queued.')
        """,
        operation_id,
        candidate_user["user_id"],
        candidate_user["candidate_id"],
        kind,
        job_id,
        f"worker-operation:{operation_id}",
    )
    return (
        operation_id,
        job_id,
        {
            "id": str(job_id),
            "kind": kind,
            "payload": {"operation_id": str(operation_id)},
            "attempts": attempts,
            "max_attempts": max_attempts,
        },
    )


@pytest.mark.asyncio
async def test_linked_job_success_keeps_queue_and_operation_consistent(
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    kind = "integration_operation_success"
    async with db_conn.transaction():
        operation = await enqueue_ai_operation(
            db_conn,
            user_id=uuid.UUID(candidate_user["user_id"]),
            candidate_id=uuid.UUID(candidate_user["candidate_id"]),
            kind=kind,
            payload={"test": "no-op"},
            idempotency_key=f"worker-operation:{uuid.uuid4()}",
        )
    operation_id = operation.id
    queued = await db_conn.fetchrow(
        """
        SELECT j.id, j.status
        FROM public.background_jobs j
        JOIN public.ai_operations o ON o.background_job_id = j.id
        WHERE o.id = $1
        """,
        operation_id,
    )
    assert queued is not None
    assert queued["status"] == "pending"
    job = await claim_next_job(
        db_conn,
        worker_id="integration-operation-worker",
        kinds=frozenset({kind}),
    )
    assert job is not None
    job_id = uuid.UUID(job["id"])
    assert job_id == queued["id"]
    result_id = uuid.uuid4()

    async def _noop(_settings: Settings, _payload: dict[str, Any]) -> HandlerResult:
        status = await db_conn.fetchval(
            "SELECT status FROM public.ai_operations WHERE id = $1",
            operation_id,
        )
        assert status == "running"
        return HandlerResult(result_type="test_result", result_id=result_id)

    bj._HANDLERS[kind] = _noop
    try:
        settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
        await process_job(ConnectionPoolShim(db_conn), settings, job)
    finally:
        bj._HANDLERS.pop(kind, None)

    row = await db_conn.fetchrow(
        """
        SELECT o.status AS operation_status, o.progress_percent, o.result_type, o.result_id,
               j.status AS job_status
        FROM public.ai_operations o
        JOIN public.background_jobs j ON j.id = o.background_job_id
        WHERE o.id = $1 AND j.id = $2
        """,
        operation_id,
        job_id,
    )
    assert dict(row) == {
        "operation_status": "succeeded",
        "progress_percent": 100,
        "result_type": "test_result",
        "result_id": result_id,
        "job_status": "completed",
    }


@pytest.mark.asyncio
async def test_linked_job_final_failure_keeps_terminal_states_consistent(
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    operation_id, job_id, job = await _insert_linked_running_job(
        db_conn,
        candidate_user,
        kind="integration_operation_failure",
        attempts=1,
        max_attempts=1,
    )

    async def _fail(_settings: Settings, _payload: dict[str, Any]) -> None:
        raise TimeoutError("private provider detail")

    bj._HANDLERS[job["kind"]] = _fail
    try:
        settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
        await process_job(ConnectionPoolShim(db_conn), settings, job)
    finally:
        bj._HANDLERS.pop(job["kind"], None)

    row = await db_conn.fetchrow(
        """
        SELECT o.status AS operation_status, o.error_code, j.status AS job_status
        FROM public.ai_operations o
        JOIN public.background_jobs j ON j.id = o.background_job_id
        WHERE o.id = $1 AND j.id = $2
        """,
        operation_id,
        job_id,
    )
    assert dict(row) == {
        "operation_status": "failed",
        "error_code": "provider_timeout",
        "job_status": "failed",
    }


@pytest.mark.asyncio
async def test_linked_job_retry_keeps_operation_running_and_queue_pending(
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    operation_id, job_id, job = await _insert_linked_running_job(
        db_conn,
        candidate_user,
        kind="integration_operation_retry",
        attempts=1,
        max_attempts=2,
    )

    async def _fail(_settings: Settings, _payload: dict[str, Any]) -> None:
        raise TimeoutError("private provider detail")

    bj._HANDLERS[job["kind"]] = _fail
    try:
        settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
        await process_job(ConnectionPoolShim(db_conn), settings, job)
    finally:
        bj._HANDLERS.pop(job["kind"], None)

    row = await db_conn.fetchrow(
        """
        SELECT o.status AS operation_status, o.stage, o.completed_at,
               j.status AS job_status, j.run_after > NOW() AS retry_delayed
        FROM public.ai_operations o
        JOIN public.background_jobs j ON j.id = o.background_job_id
        WHERE o.id = $1 AND j.id = $2
        """,
        operation_id,
        job_id,
    )
    assert row["operation_status"] == "running"
    assert row["stage"] == "retry_scheduled"
    assert row["completed_at"] is None
    assert row["job_status"] == "pending"
    assert row["retry_delayed"] is True


@pytest.mark.asyncio
async def test_linked_job_cancel_race_discards_late_success(
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    operation_id, job_id, job = await _insert_linked_running_job(
        db_conn, candidate_user, kind="integration_operation_cancel_race"
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def _blocked(_settings: Settings, _payload: dict[str, Any]) -> HandlerResult:
        started.set()
        await release.wait()
        return HandlerResult(result_type="test_result", result_id=uuid.uuid4())

    bj._HANDLERS[job["kind"]] = _blocked
    try:
        settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
        task = asyncio.create_task(process_job(ConnectionPoolShim(db_conn), settings, job))
        await started.wait()
        async with db_conn.transaction():
            await db_conn.execute(
                """
                UPDATE public.ai_operations
                SET status = 'cancelled', stage = 'cancelled', message = 'Cancelled.',
                    error_code = 'cancelled', error_message = 'Cancelled.', completed_at = NOW()
                WHERE id = $1 AND status = 'running'
                """,
                operation_id,
            )
            await db_conn.execute(
                """
                UPDATE public.background_jobs
                SET status = 'cancelled', completed_at = NOW()
                WHERE id = $1 AND status = 'running'
                """,
                job_id,
            )
        release.set()
        await task
    finally:
        bj._HANDLERS.pop(job["kind"], None)

    row = await db_conn.fetchrow(
        """
        SELECT o.status AS operation_status, o.result_id, j.status AS job_status
        FROM public.ai_operations o
        JOIN public.background_jobs j ON j.id = o.background_job_id
        WHERE o.id = $1 AND j.id = $2
        """,
        operation_id,
        job_id,
    )
    assert dict(row) == {
        "operation_status": "cancelled",
        "result_id": None,
        "job_status": "cancelled",
    }
