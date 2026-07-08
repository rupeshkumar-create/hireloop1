"""Unit tests for the durable background_jobs queue."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from hireloop_api.config import Settings
from hireloop_api.services import background_jobs as bj
from hireloop_api.services.background_jobs import (
    AARYA_AUTO_INGEST,
    claim_next_job,
    enqueue_job,
    mark_job_failed,
    process_job,
)
from tests.pool_shim import ConnectionPoolShim


class _JobDB:
    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, dict[str, Any]] = {}

    async def fetchval(self, query: str, *args: object) -> object | None:
        if "SELECT id FROM public.background_jobs" in query and "idempotency_key" in query:
            key = args[0]
            for job in self.jobs.values():
                if job.get("idempotency_key") == key and job["status"] in (
                    "pending",
                    "running",
                ):
                    return job["id"]
            return None
        if "INSERT INTO public.background_jobs" in query:
            job_id = uuid.uuid4()
            self.jobs[job_id] = {
                "id": job_id,
                "kind": args[0],
                "payload": json.loads(str(args[1])),
                "idempotency_key": args[2],
                "status": "pending",
                "attempts": 0,
                "max_attempts": args[4],
                "run_after": args[3],
            }
            return job_id
        return None

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FOR UPDATE SKIP LOCKED" in query:
            pending = [
                j
                for j in self.jobs.values()
                if j["status"] == "pending" and j["run_after"] <= datetime.now(UTC)
            ]
            if not pending:
                return None
            job = sorted(pending, key=lambda j: j["run_after"])[0]
            job["status"] = "running"
            job["attempts"] += 1
            return {
                "id": job["id"],
                "kind": job["kind"],
                "payload": job["payload"],
                "attempts": job["attempts"],
                "max_attempts": job["max_attempts"],
            }
        return None

    async def execute(self, query: str, *args: object) -> str:
        job_id = uuid.UUID(str(args[0]))
        if "status = 'completed'" in query:
            self.jobs[job_id]["status"] = "completed"
        elif "status = 'failed'" in query:
            self.jobs[job_id]["status"] = "failed"
        elif "status = 'pending'" in query and "last_error" in query:
            self.jobs[job_id]["status"] = "pending"
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_enqueue_idempotency() -> None:
    db = _JobDB()
    payload = {"candidate_id": "abc"}
    first = await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=AARYA_AUTO_INGEST,
        payload=payload,
        idempotency_key="dup",
    )
    second = await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=AARYA_AUTO_INGEST,
        payload=payload,
        idempotency_key="dup",
    )
    assert first == second
    assert len(db.jobs) == 1


@pytest.mark.asyncio
async def test_claim_and_complete() -> None:
    db = _JobDB()
    job_id = await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=AARYA_AUTO_INGEST,
        payload={"candidate_id": "x"},
    )
    claimed = await claim_next_job(db, worker_id="w1")  # type: ignore[arg-type]
    assert claimed is not None
    assert claimed["id"] == str(job_id)

    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]

    async def _noop(_settings: Settings, payload: dict[str, Any]) -> None:
        assert payload["candidate_id"] == "x"

    original = bj._HANDLERS[AARYA_AUTO_INGEST]
    bj._HANDLERS[AARYA_AUTO_INGEST] = _noop
    try:
        await process_job(ConnectionPoolShim(db), settings, claimed)  # type: ignore[arg-type]
    finally:
        bj._HANDLERS[AARYA_AUTO_INGEST] = original

    assert db.jobs[job_id]["status"] == "completed"


@pytest.mark.asyncio
async def test_mark_failed_retries_then_dead() -> None:
    db = _JobDB()
    job_id = uuid.uuid4()
    db.jobs[job_id] = {
        "id": job_id,
        "status": "running",
        "attempts": 1,
        "max_attempts": 2,
        "run_after": datetime.now(UTC),
    }
    await mark_job_failed(
        db,  # type: ignore[arg-type]
        str(job_id),
        error="boom",
        attempts=1,
        max_attempts=2,
    )
    assert db.jobs[job_id]["status"] == "pending"

    await mark_job_failed(
        db,  # type: ignore[arg-type]
        str(job_id),
        error="boom again",
        attempts=2,
        max_attempts=2,
    )
    assert db.jobs[job_id]["status"] == "failed"


@pytest.mark.asyncio
async def test_career_path_ingest_derives_from_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    async def _fake_candidate_ingest(
        settings: Settings,
        candidate_id: str,
        *,
        force_refresh: bool = False,
        requested_titles: list[str] | None = None,
        requested_locations: list[str] | None = None,
    ) -> None:
        called["candidate_id"] = candidate_id
        called["force_refresh"] = force_refresh
        called["requested_titles"] = requested_titles
        called["requested_locations"] = requested_locations

    async def _fail_raw_ingest(
        settings: Settings,
        candidate_id: str,
        queries: list[str],
        locations: list[str],
    ) -> None:
        raise AssertionError("raw query ingest should not run for derived candidate payload")

    monkeypatch.setattr(
        "hireloop_api.routes.career._ingest_candidate_and_rescore",
        _fake_candidate_ingest,
    )
    monkeypatch.setattr(
        "hireloop_api.routes.career._ingest_and_rescore",
        _fail_raw_ingest,
    )

    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await bj._handle_career_path_ingest(
        settings,
        {
            "candidate_id": "11111111-1111-1111-1111-111111111111",
            "derive_from_candidate": True,
            "force_refresh": True,
            "requested_titles": ["UI/UX Designer"],
            "locations": ["Bengaluru"],
        },
    )

    assert called["candidate_id"] == "11111111-1111-1111-1111-111111111111"
    assert called["force_refresh"] is True
    assert called["requested_titles"] == ["UI/UX Designer"]
    assert called["requested_locations"] == ["Bengaluru"]


@pytest.mark.asyncio
async def test_application_kit_handler_runs_candidate_job_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    async def _fake_run(settings: Settings, candidate_id: str, job_id: str) -> None:
        called["candidate_id"] = candidate_id
        called["job_id"] = job_id

    monkeypatch.setattr(
        "hireloop_api.services.application_kit.run_application_kit_job",
        _fake_run,
    )

    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await bj._handle_application_kit(
        settings,
        {
            "candidate_id": "11111111-1111-1111-1111-111111111111",
            "job_id": "22222222-2222-2222-2222-222222222222",
        },
    )

    assert called == {
        "candidate_id": "11111111-1111-1111-1111-111111111111",
        "job_id": "22222222-2222-2222-2222-222222222222",
    }
    assert bj.APPLICATION_KIT == "application_kit"
