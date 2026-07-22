"""Unit tests for the durable background_jobs queue."""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from hireloop_api.config import Settings
from hireloop_api.services import background_jobs as bj
from hireloop_api.services.background_jobs import (
    _INTERACTIVE_JOB_KINDS,
    AARYA_AUTO_INGEST,
    APPLICATION_KIT,
    HandlerResult,
    claim_next_job,
    enqueue_job,
    mark_job_failed,
    process_job,
    publish_operation_progress,
)
from tests.pool_shim import ConnectionPoolShim


async def _persist_nothing(_db: asyncpg.Connection) -> None:
    return None


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
            # WHERE filters live before ORDER BY; $2 is always the interactive priority list.
            where_sql = query.split("ORDER BY", 1)[0]
            kinds: set[str] | None = None
            exclude: set[str] | None = None
            if "kind = ANY(" in where_sql:
                # kinds filter is the first *extra* bind after worker + interactive list.
                kinds = {str(k) for k in (args[2] or [])}  # type: ignore[arg-type]
            if "kind <> ALL(" in where_sql:
                excl_idx = 3 if "kind = ANY(" in where_sql else 2
                exclude = {str(k) for k in (args[excl_idx] or [])}  # type: ignore[arg-type]
            if kinds is not None:
                pending = [j for j in pending if j["kind"] in kinds]
            if exclude is not None:
                pending = [j for j in pending if j["kind"] not in exclude]
            if not pending:
                return None
            interactive = {str(k) for k in (args[1] or [])} if len(args) >= 2 else set()  # type: ignore[arg-type]

            def _prio(j: dict[str, Any]) -> tuple[int, datetime, Any]:
                return (
                    0 if j["kind"] in interactive else 1,
                    j["run_after"],
                    j["id"],
                )

            job = sorted(pending, key=_prio)[0]
            job["status"] = "running"
            job["worker_id"] = str(args[0])
            job["attempts"] += 1
            return {
                "id": job["id"],
                "kind": job["kind"],
                "payload": job["payload"],
                "attempts": job["attempts"],
                "max_attempts": job["max_attempts"],
                "worker_id": job["worker_id"],
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

    @asynccontextmanager
    async def transaction(self):  # type: ignore[no-untyped-def]
        yield


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
        "worker_id": "test-worker",
        "run_after": datetime.now(UTC),
    }
    await mark_job_failed(
        db,  # type: ignore[arg-type]
        str(job_id),
        error="boom",
        attempts=1,
        max_attempts=2,
        worker_id="test-worker",
    )
    assert db.jobs[job_id]["status"] == "pending"

    await mark_job_failed(
        db,  # type: ignore[arg-type]
        str(job_id),
        error="boom again",
        attempts=2,
        max_attempts=2,
        worker_id="test-worker",
    )
    assert db.jobs[job_id]["status"] == "failed"


@pytest.mark.asyncio
async def test_claim_prefers_application_kit_over_older_ingest() -> None:
    """Interactive kits must jump ahead of earlier Apify ingest jobs."""
    db = _JobDB()
    earlier = datetime.now(UTC)
    await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=AARYA_AUTO_INGEST,
        payload={"candidate_id": "heavy"},
        run_after=earlier,
    )
    kit_id = await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=APPLICATION_KIT,
        payload={"candidate_id": "ui", "job_id": "j1"},
        run_after=earlier,
    )
    claimed = await claim_next_job(db, worker_id="w1")  # type: ignore[arg-type]
    assert claimed is not None
    assert claimed["id"] == str(kit_id)
    assert claimed["kind"] == APPLICATION_KIT


@pytest.mark.asyncio
async def test_claim_interactive_lane_skips_heavy_kinds() -> None:
    db = _JobDB()
    await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=AARYA_AUTO_INGEST,
        payload={"candidate_id": "heavy"},
    )
    kit_id = await enqueue_job(
        db,  # type: ignore[arg-type]
        kind=APPLICATION_KIT,
        payload={"candidate_id": "ui", "job_id": "j1"},
    )
    claimed = await claim_next_job(
        db,  # type: ignore[arg-type]
        worker_id="w-ui",
        kinds=_INTERACTIVE_JOB_KINDS,
    )
    assert claimed is not None
    assert claimed["id"] == str(kit_id)

    heavy = await claim_next_job(
        db,  # type: ignore[arg-type]
        worker_id="w-heavy",
        exclude_kinds=_INTERACTIVE_JOB_KINDS,
    )
    assert heavy is not None
    assert heavy["kind"] == AARYA_AUTO_INGEST


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
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        called["candidate_id"] = candidate_id
        called["force_refresh"] = force_refresh
        called["requested_titles"] = requested_titles
        called["requested_locations"] = requested_locations
        called["user_id"] = user_id
        called["session_id"] = session_id

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


@pytest.mark.asyncio
async def test_linked_operation_runs_before_handler_and_completes_with_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = uuid.uuid4()
    result_id = uuid.uuid4()
    events: list[str] = []

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        events.append("operation-running")
        return True

    async def _complete(*_args: object, **kwargs: object) -> bool:
        result = kwargs["result"]
        assert result == HandlerResult(
            result_type="career_path", result_id=result_id, persist=_persist_nothing
        )
        events.append("operation-and-job-succeeded")
        return True

    async def _handler(_settings: Settings, _payload: dict[str, Any]) -> HandlerResult:
        assert _payload["_job_lease_token"] == "test-worker"
        events.append("handler")
        return HandlerResult(
            result_type="career_path", result_id=result_id, persist=_persist_nothing
        )

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setattr(bj, "_complete_linked_operation", _complete)
    monkeypatch.setitem(bj._HANDLERS, "linked-test", _handler)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]

    await process_job(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": "linked-test",
            "payload": {"operation_id": str(operation_id)},
            "attempts": 1,
            "max_attempts": 3,
            "worker_id": "test-worker",
        },
    )

    assert events == ["operation-running", "handler", "operation-and-job-succeeded"]


@pytest.mark.asyncio
async def test_linked_operation_requires_valid_result_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[BaseException] = []

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        return True

    async def _fail(*_args: object, **kwargs: object) -> None:
        failures.append(kwargs["error"])

    async def _legacy_result(_settings: Settings, _payload: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setattr(bj, "_fail_linked_operation", _fail)
    monkeypatch.setitem(bj._HANDLERS, "linked-invalid-result", _legacy_result)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]

    await process_job(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": "linked-invalid-result",
            "payload": {"operation_id": str(uuid.uuid4())},
            "attempts": 3,
            "max_attempts": 3,
            "worker_id": "test-worker",
        },
    )

    assert len(failures) == 1
    assert "result reference" in str(failures[0]).lower()


@pytest.mark.asyncio
async def test_linked_retry_keeps_operation_nonterminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[tuple[int, int]] = []

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        return True

    async def _fail(*_args: object, **kwargs: object) -> None:
        failures.append((int(kwargs["attempts"]), int(kwargs["max_attempts"])))

    async def _boom(_settings: Settings, _payload: dict[str, Any]) -> None:
        raise TimeoutError("private provider detail")

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setattr(bj, "_fail_linked_operation", _fail)
    monkeypatch.setitem(bj._HANDLERS, "linked-retry", _boom)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]

    await process_job(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": "linked-retry",
            "payload": {"operation_id": str(uuid.uuid4())},
            "attempts": 1,
            "max_attempts": 3,
            "worker_id": "test-worker",
        },
    )

    assert failures == [(1, 3)]


@pytest.mark.asyncio
async def test_cancel_while_handler_blocked_discards_late_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = uuid.uuid4()
    started = asyncio.Event()
    release = asyncio.Event()
    state = {"operation": "running", "queue": "running"}
    success_calls = 0

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        return True

    async def _handler(_settings: Settings, _payload: dict[str, Any]) -> HandlerResult:
        started.set()
        await release.wait()
        return HandlerResult(
            result_type="application_kit", result_id=uuid.uuid4(), persist=_persist_nothing
        )

    async def _complete(*_args: object, **_kwargs: object) -> bool:
        nonlocal success_calls
        if state["operation"] != "running" or state["queue"] != "running":
            return False
        success_calls += 1
        state.update(operation="succeeded", queue="completed")
        return True

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setattr(bj, "_complete_linked_operation", _complete)
    monkeypatch.setitem(bj._HANDLERS, "cancel-race", _handler)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    task = asyncio.create_task(
        process_job(
            ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
            settings,
            {
                "id": str(uuid.uuid4()),
                "kind": "cancel-race",
                "payload": {"operation_id": str(operation_id)},
                "attempts": 1,
                "max_attempts": 3,
                "worker_id": "test-worker",
            },
        )
    )
    await started.wait()
    state.update(operation="cancelled", queue="cancelled")
    release.set()
    await task

    assert success_calls == 0
    assert state == {"operation": "cancelled", "queue": "cancelled"}


@pytest.mark.asyncio
async def test_progress_helper_ignores_legacy_payloads() -> None:
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await publish_operation_progress(
        settings,
        {"candidate_id": "legacy"},
        progress_percent=25,
        stage="generating",
        message="Generating.",
    )


@pytest.mark.asyncio
async def test_progress_helper_rejects_linked_payload_without_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = uuid.uuid4()
    pool_called = False

    async def _pool(_settings: Settings) -> ConnectionPoolShim:
        nonlocal pool_called
        pool_called = True
        return ConnectionPoolShim(_JobDB())  # type: ignore[arg-type]

    monkeypatch.setattr("hireloop_api.deps.get_db_pool", _pool)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await publish_operation_progress(
        settings,
        {"operation_id": str(operation_id)},
        progress_percent=45,
        stage="generating",
        message="Generating your result.",
    )
    assert pool_called is False


@pytest.mark.asyncio
async def test_cancelled_operation_is_released_before_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler_called = False

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        return False

    async def _handler(_settings: Settings, _payload: dict[str, Any]) -> HandlerResult:
        nonlocal handler_called
        handler_called = True
        return HandlerResult(result_type="test", result_id=uuid.uuid4(), persist=_persist_nothing)

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setitem(bj._HANDLERS, "cancelled-before-start", _handler)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await process_job(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": "cancelled-before-start",
            "payload": {"operation_id": str(uuid.uuid4())},
            "attempts": 1,
            "max_attempts": 3,
            "worker_id": "test-worker",
        },
    )
    assert handler_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("attempts", "max_attempts"), [(1, 3), (3, 3)])
async def test_unknown_linked_handler_uses_operation_failure_path(
    monkeypatch: pytest.MonkeyPatch,
    attempts: int,
    max_attempts: int,
) -> None:
    failures: list[tuple[str, int, int]] = []

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        return True

    async def _fail(*_args: object, **kwargs: object) -> None:
        failures.append(
            (
                str(kwargs["error"]),
                int(kwargs["attempts"]),
                int(kwargs["max_attempts"]),
            )
        )

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setattr(bj, "_fail_linked_operation", _fail)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await process_job(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": f"unknown-linked-{uuid.uuid4()}",
            "payload": {"operation_id": str(uuid.uuid4())},
            "attempts": attempts,
            "max_attempts": max_attempts,
            "worker_id": "test-worker",
        },
    )
    assert len(failures) == 1
    assert failures[0][1:] == (attempts, max_attempts)
    assert "unknown job kind" in failures[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("invalid"), PermissionError("denied")])
async def test_non_retryable_linked_error_fails_immediately(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    operation_id = uuid.uuid4()
    queue_calls: list[tuple[int, int]] = []
    operation_failures: list[BaseException] = []
    progress_calls = 0

    async def _state(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "operation_status": "running",
            "job_status": "running",
            "worker_id": "test-worker",
            "progress_percent": 20,
        }

    async def _queue_fail(
        _db: object,
        _job_id: str,
        *,
        error: str,
        attempts: int,
        max_attempts: int,
        worker_id: str,
    ) -> bool:
        queue_calls.append((attempts, max_attempts))
        return True

    async def _operation_fail(
        _db: object, _operation_id: uuid.UUID, failure: BaseException
    ) -> object:
        operation_failures.append(failure)
        return SimpleNamespace(status="failed")

    async def _progress(*_args: object, **_kwargs: object) -> object:
        nonlocal progress_calls
        progress_calls += 1
        return object()

    monkeypatch.setattr(bj, "_linked_state", _state)
    monkeypatch.setattr(bj, "mark_job_failed", _queue_fail)
    monkeypatch.setattr(
        "hireloop_api.services.ai_operations.mark_operation_failed", _operation_fail
    )
    monkeypatch.setattr("hireloop_api.services.ai_operations.update_operation_progress", _progress)

    await bj._fail_linked_operation(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        operation_id=operation_id,
        job_id=str(uuid.uuid4()),
        error=error,
        attempts=1,
        max_attempts=3,
        worker_id="test-worker",
    )

    assert operation_failures == [error]
    assert queue_calls == [(1, 1)]
    assert progress_calls == 0


@pytest.mark.asyncio
async def test_transient_linked_error_schedules_retry_without_terminal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = uuid.uuid4()
    queue_calls: list[tuple[int, int]] = []
    operation_failures = 0
    progress_stages: list[str] = []

    async def _state(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "operation_status": "running",
            "job_status": "running",
            "worker_id": "test-worker",
            "progress_percent": 20,
        }

    async def _queue_fail(
        _db: object,
        _job_id: str,
        *,
        error: str,
        attempts: int,
        max_attempts: int,
        worker_id: str,
    ) -> bool:
        queue_calls.append((attempts, max_attempts))
        return True

    async def _operation_fail(*_args: object, **_kwargs: object) -> object:
        nonlocal operation_failures
        operation_failures += 1
        return SimpleNamespace(status="failed")

    async def _progress(
        _db: object,
        _operation_id: uuid.UUID,
        _percent: int,
        stage: str,
        _message: str,
    ) -> object:
        progress_stages.append(stage)
        return object()

    monkeypatch.setattr(bj, "_linked_state", _state)
    monkeypatch.setattr(bj, "mark_job_failed", _queue_fail)
    monkeypatch.setattr(
        "hireloop_api.services.ai_operations.mark_operation_failed", _operation_fail
    )
    monkeypatch.setattr("hireloop_api.services.ai_operations.update_operation_progress", _progress)

    await bj._fail_linked_operation(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        operation_id=operation_id,
        job_id=str(uuid.uuid4()),
        error=TimeoutError("provider timed out"),
        attempts=1,
        max_attempts=3,
        worker_id="test-worker",
    )

    assert queue_calls == [(1, 3)]
    assert operation_failures == 0
    assert progress_stages == ["retry_scheduled"]


@pytest.mark.asyncio
@pytest.mark.parametrize("handler_mode", ["unknown", "missing_result"])
async def test_programming_errors_from_process_fail_linked_job_immediately(
    monkeypatch: pytest.MonkeyPatch,
    handler_mode: str,
) -> None:
    operation_failures: list[BaseException] = []
    queue_calls: list[tuple[int, int]] = []
    kind = f"programming-error-{uuid.uuid4()}"

    async def _prepare(*_args: object, **_kwargs: object) -> bool:
        return True

    async def _state(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "operation_status": "running",
            "job_status": "running",
            "worker_id": "test-worker",
            "progress_percent": 1,
        }

    async def _operation_fail(
        _db: object, _operation_id: uuid.UUID, failure: BaseException
    ) -> object:
        operation_failures.append(failure)
        return SimpleNamespace(status="failed")

    async def _queue_fail(
        _db: object,
        _job_id: str,
        *,
        error: str,
        attempts: int,
        max_attempts: int,
        worker_id: str,
    ) -> bool:
        queue_calls.append((attempts, max_attempts))
        return True

    async def _missing_result(_settings: Settings, _payload: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(bj, "_prepare_linked_operation", _prepare)
    monkeypatch.setattr(bj, "_linked_state", _state)
    monkeypatch.setattr(bj, "mark_job_failed", _queue_fail)
    monkeypatch.setattr(
        "hireloop_api.services.ai_operations.mark_operation_failed", _operation_fail
    )
    if handler_mode == "missing_result":
        monkeypatch.setitem(bj._HANDLERS, kind, _missing_result)

    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await process_job(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": kind,
            "payload": {"operation_id": str(uuid.uuid4())},
            "attempts": 1,
            "max_attempts": 3,
            "worker_id": "test-worker",
        },
    )

    assert len(operation_failures) == 1
    assert queue_calls == [(1, 1)]


@pytest.mark.asyncio
async def test_failure_path_preserves_cancelled_operation_and_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced: list[str] = []
    terminal_calls = 0

    async def _state(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "operation_status": "cancelled",
            "job_status": "cancelled",
            "worker_id": "test-worker",
            "progress_percent": 10,
        }

    async def _sync(
        _db: object,
        *,
        job_id: str,
        operation_status: str,
        worker_id: str,
    ) -> None:
        synced.append(operation_status)

    async def _terminal(*_args: object, **_kwargs: object) -> object:
        nonlocal terminal_calls
        terminal_calls += 1
        return object()

    monkeypatch.setattr(bj, "_linked_state", _state)
    monkeypatch.setattr(bj, "_sync_queue_with_terminal_operation", _sync)
    monkeypatch.setattr("hireloop_api.services.ai_operations.mark_operation_failed", _terminal)

    await bj._fail_linked_operation(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        operation_id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        error=ValueError("late"),
        attempts=1,
        max_attempts=3,
        worker_id="test-worker",
    )
    assert synced == ["cancelled"]
    assert terminal_calls == 0


@pytest.mark.asyncio
async def test_classified_cancellation_cancels_queue_instead_of_failing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced: list[str] = []
    queue_failures = 0

    async def _state(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "operation_status": "running",
            "job_status": "running",
            "worker_id": "test-worker",
            "progress_percent": 10,
        }

    async def _operation_fail(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(status="cancelled")

    async def _sync(
        _db: object,
        *,
        job_id: str,
        operation_status: str,
        worker_id: str,
    ) -> None:
        synced.append(operation_status)

    async def _queue_fail(*_args: object, **_kwargs: object) -> bool:
        nonlocal queue_failures
        queue_failures += 1
        return True

    monkeypatch.setattr(bj, "_linked_state", _state)
    monkeypatch.setattr(bj, "_sync_queue_with_terminal_operation", _sync)
    monkeypatch.setattr(bj, "mark_job_failed", _queue_fail)
    monkeypatch.setattr(
        "hireloop_api.services.ai_operations.mark_operation_failed", _operation_fail
    )

    await bj._fail_linked_operation(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        operation_id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        error=RuntimeError("cancelled by candidate"),
        attempts=1,
        max_attempts=3,
        worker_id="test-worker",
    )
    assert synced == ["cancelled"]
    assert queue_failures == 0


@pytest.mark.asyncio
async def test_old_worker_lease_cannot_persist_or_finalize_linked_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[str] = []

    async def _state(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {
            "operation_status": "running",
            "job_status": "running",
            "worker_id": "new-worker",
            "progress_percent": 20,
        }

    async def _persist(_db: asyncpg.Connection) -> None:
        persisted.append("written")

    monkeypatch.setattr(bj, "_linked_state", _state)
    completed = await bj._complete_linked_operation(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        operation_id=uuid.uuid4(),
        job_id=str(uuid.uuid4()),
        worker_id="old-worker",
        result=HandlerResult(
            result_type="test_result",
            result_id=uuid.uuid4(),
            persist=_persist,
        ),
    )
    assert completed is False
    assert persisted == []


@pytest.mark.asyncio
async def test_heartbeat_renews_lease_periodically_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    renewals: list[tuple[str, str]] = []

    async def _renew(
        _pool: object,
        *,
        job_id: str,
        worker_id: str,
    ) -> bool:
        renewals.append((job_id, worker_id))
        if len(renewals) == 2:
            stop.set()
        return True

    monkeypatch.setattr(bj, "_renew_job_lease", _renew)
    await bj._heartbeat_job_lease(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        job_id="00000000-0000-0000-0000-000000000001",
        worker_id="lease-owner",
        stop_event=stop,
        interval_seconds=0.001,
    )
    assert renewals == [
        ("00000000-0000-0000-0000-000000000001", "lease-owner"),
        ("00000000-0000-0000-0000-000000000001", "lease-owner"),
    ]


@pytest.mark.asyncio
async def test_claims_from_same_lane_receive_unique_lease_tokens() -> None:
    db = _JobDB()
    await enqueue_job(db, kind=AARYA_AUTO_INGEST, payload={"candidate_id": "one"})  # type: ignore[arg-type]
    await enqueue_job(db, kind=AARYA_AUTO_INGEST, payload={"candidate_id": "two"})  # type: ignore[arg-type]
    first = await claim_next_job(db, worker_id="same-lane")  # type: ignore[arg-type]
    second = await claim_next_job(db, worker_id="same-lane")  # type: ignore[arg-type]
    assert first is not None and second is not None
    assert first["worker_id"] != second["worker_id"]
    assert str(first["worker_id"]).startswith("same-lane:")
    assert str(second["worker_id"]).startswith("same-lane:")


@pytest.mark.asyncio
async def test_heartbeat_recovers_after_transient_renew_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    calls = 0

    async def _renew(*_args: object, **_kwargs: object) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("temporary pool failure")
        stop.set()
        return True

    monkeypatch.setattr(bj, "_renew_job_lease", _renew)
    await bj._heartbeat_job_lease(
        ConnectionPoolShim(_JobDB()),  # type: ignore[arg-type]
        job_id=str(uuid.uuid4()),
        worker_id="unique-lease",
        stop_event=stop,
        interval_seconds=0.001,
    )
    assert calls == 2


@pytest.mark.asyncio
async def test_heartbeat_cleanup_failure_does_not_override_handler_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _JobDB()
    job_id = uuid.uuid4()
    db.jobs[job_id] = {
        "id": job_id,
        "kind": "heartbeat-cleanup",
        "status": "running",
        "worker_id": "unique-lease",
        "attempts": 1,
        "max_attempts": 3,
        "run_after": datetime.now(UTC),
    }

    async def _broken_heartbeat(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("heartbeat cleanup failed")

    async def _success(_settings: Settings, _payload: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(bj, "_heartbeat_job_lease", _broken_heartbeat)
    monkeypatch.setitem(bj._HANDLERS, "heartbeat-cleanup", _success)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await process_job(
        ConnectionPoolShim(db),  # type: ignore[arg-type]
        settings,
        {
            "id": str(job_id),
            "kind": "heartbeat-cleanup",
            "payload": {},
            "attempts": 1,
            "max_attempts": 3,
            "worker_id": "unique-lease",
        },
    )
    assert db.jobs[job_id]["status"] == "completed"


@pytest.mark.asyncio
async def test_old_lease_cannot_decline_nitya_intro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intro_updates = 0

    class _NityaDB(_JobDB):
        async def execute(self, query: str, *args: object) -> str:
            nonlocal intro_updates
            if "UPDATE public.intro_requests" in query:
                intro_updates += 1
                return "UPDATE 1"
            return await super().execute(query, *args)

    async def _lost_lease(*_args: object, **_kwargs: object) -> bool:
        return False

    async def _fail(_settings: Settings, _payload: dict[str, Any]) -> None:
        raise RuntimeError("terminal failure")

    monkeypatch.setattr(bj, "mark_job_failed", _lost_lease)
    monkeypatch.setitem(bj._HANDLERS, bj.NITYA_INTRO_DRAFT, _fail)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await process_job(
        ConnectionPoolShim(_NityaDB()),  # type: ignore[arg-type]
        settings,
        {
            "id": str(uuid.uuid4()),
            "kind": bj.NITYA_INTRO_DRAFT,
            "payload": {"id": str(uuid.uuid4())},
            "attempts": 3,
            "max_attempts": 3,
            "worker_id": "old-lease",
        },
    )
    assert intro_updates == 0


@pytest.mark.asyncio
async def test_progress_requires_current_queue_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = uuid.uuid4()
    calls: list[tuple[str, tuple[object, ...]]] = []

    class _ProgressDB(_JobDB):
        async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
            calls.append((query, args))
            return None

    async def _pool(_settings: Settings) -> ConnectionPoolShim:
        return ConnectionPoolShim(_ProgressDB())  # type: ignore[arg-type]

    monkeypatch.setattr("hireloop_api.deps.get_db_pool", _pool)
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await publish_operation_progress(
        settings,
        {"operation_id": str(operation_id), "_job_lease_token": "current-lease"},
        progress_percent=30,
        stage="generating",
        message="Generating.",
    )
    assert len(calls) == 1
    query, args = calls[0]
    assert "FROM public.background_jobs" in query
    assert "j.worker_id = $2" in query
    assert args[:2] == (operation_id, "current-lease")


@pytest.mark.asyncio
async def test_linked_state_locks_operation_before_queue() -> None:
    operation_id = uuid.uuid4()
    job_id = uuid.uuid4()
    queries: list[str] = []

    class _LockDB(_JobDB):
        async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
            queries.append(query)
            if "FROM public.ai_operations" in query:
                return {
                    "operation_status": "running",
                    "progress_percent": 10,
                    "background_job_id": job_id,
                }
            return {"job_status": "running", "worker_id": "lease"}

    state = await bj._linked_state(_LockDB(), operation_id, str(job_id))  # type: ignore[arg-type]
    assert state is not None
    assert len(queries) == 2
    assert "FROM public.ai_operations" in queries[0]
    assert "FOR UPDATE" in queries[0]
    assert "FROM public.background_jobs" in queries[1]
    assert "FOR UPDATE" in queries[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("link_mode", ["invalid_payload", "broken_link"])
async def test_corrupt_operation_link_terminally_fails_claimed_queue(
    monkeypatch: pytest.MonkeyPatch,
    link_mode: str,
) -> None:
    db = _JobDB()
    job_id = uuid.uuid4()
    payload = {"operation_id": "not-a-uuid"}
    if link_mode == "broken_link":
        payload = {"operation_id": str(uuid.uuid4())}

        async def _broken(*_args: object, **_kwargs: object) -> bool:
            raise ValueError("Queue job is not linked to its AI operation")

        monkeypatch.setattr(bj, "_prepare_linked_operation", _broken)
    db.jobs[job_id] = {
        "id": job_id,
        "kind": "corrupt-linked-job",
        "status": "running",
        "worker_id": "test-worker",
        "attempts": 1,
        "max_attempts": 3,
        "run_after": datetime.now(UTC),
    }
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    await process_job(
        ConnectionPoolShim(db),  # type: ignore[arg-type]
        settings,
        {
            "id": str(job_id),
            "kind": "corrupt-linked-job",
            "payload": payload,
            "attempts": 1,
            "max_attempts": 3,
            "worker_id": "test-worker",
        },
    )
    assert db.jobs[job_id]["status"] == "failed"
