"""Unit coverage for the user-safe durable AI operation lifecycle."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from hireloop_api.models.ai_operation import AiOperationAccepted, AiOperationResponse
from hireloop_api.services import ai_operations

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
USER_ID = uuid.uuid4()
OPERATION_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _operation_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": OPERATION_ID,
        "kind": "application_kit",
        "status": "queued",
        "progress_percent": 0,
        "stage": "queued",
        "message": "Your application kit is queued.",
        "result_type": None,
        "result_id": None,
        "error_code": None,
        "error_message": None,
        "created_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
    }
    row.update(overrides)
    return row


class ScriptedConnection:
    """Small asyncpg-shaped test double with explicitly scripted results."""

    def __init__(
        self,
        *,
        fetchrows: list[dict[str, object] | None] | None = None,
        fetchvals: list[object] | None = None,
        fetch_result: list[dict[str, object]] | None = None,
    ) -> None:
        self.fetchrows = list(fetchrows or [])
        self.fetchvals = list(fetchvals or [])
        self.fetch_result = list(fetch_result or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrows.pop(0) if self.fetchrows else None

    async def fetchval(self, query: str, *args: object) -> object:
        self.calls.append(("fetchval", query, args))
        return self.fetchvals.pop(0) if self.fetchvals else None

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.calls.append(("fetch", query, args))
        return self.fetch_result

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append(("execute", query, args))
        return "UPDATE 1"


def test_response_serialization_omits_private_queue_and_raw_error_fields() -> None:
    response = AiOperationResponse.model_validate(
        {
            **_operation_row(),
            "payload": {"resume_text": "private"},
            "last_error": "provider response included a secret",
            "worker_id": "worker-1",
        }
    )

    serialized = response.model_dump(mode="json")
    assert "payload" not in serialized
    assert "last_error" not in serialized
    assert "worker_id" not in serialized
    assert response.retryable is False


def test_accepted_response_uses_the_approved_polling_contract() -> None:
    accepted = AiOperationAccepted(
        operation_id=OPERATION_ID,
        status="queued",
        status_url=f"/api/v1/ai-operations/{OPERATION_ID}",
    )

    assert accepted.retry_after_ms == 1500


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (TimeoutError("secret timeout detail"), "provider_timeout", True),
        (RuntimeError("HTTP 429 from provider"), "provider_rate_limited", True),
        (ConnectionError("provider unavailable"), "provider_unavailable", True),
        (OSError("DNS network unreachable: secret.internal"), "network_unreachable", True),
        (OSError("local disk is full"), "internal_error", False),
        (ValueError("malformed provider response"), "invalid_input", False),
        (RuntimeError("candidate profile is insufficient"), "insufficient_profile", False),
        (PermissionError("forbidden"), "permission_denied", False),
        (RuntimeError("job has expired"), "job_expired", False),
        (asyncio.CancelledError(), "cancelled", False),
        (RuntimeError("resume text and token abc123"), "internal_error", False),
    ],
)
def test_error_classification_is_stable_and_does_not_echo_raw_errors(
    error: BaseException,
    code: str,
    retryable: bool,
) -> None:
    classified = ai_operations.classify_operation_error(error)

    assert classified.code == code
    assert classified.retryable is retryable
    if str(error):
        assert str(error) not in classified.message
    assert len(classified.message) <= ai_operations.MAX_SAFE_ERROR_MESSAGE_LENGTH


@pytest.mark.asyncio
async def test_enqueue_creates_operation_and_job_on_the_caller_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inserted = _operation_row(background_job_id=None)
    linked = _operation_row(background_job_id=JOB_ID)
    db = ScriptedConnection(fetchrows=[inserted, linked])
    observed: dict[str, object] = {}

    async def fake_enqueue_job(db_arg: object, **kwargs: object) -> uuid.UUID:
        observed["db"] = db_arg
        observed.update(kwargs)
        return JOB_ID

    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", fake_enqueue_job)

    response = await ai_operations.enqueue_ai_operation(
        db,  # type: ignore[arg-type]
        user_id=USER_ID,
        candidate_id=uuid.uuid4(),
        kind="application_kit",
        payload={"candidate_id": "private-candidate-id"},
        idempotency_key=f"application_kit:{USER_ID}:job",
        stage="queued",
        message="Your application kit is queued.",
    )

    assert response.id == OPERATION_ID
    assert observed["db"] is db
    assert observed["payload"] == {
        "candidate_id": "private-candidate-id",
        "operation_id": str(OPERATION_ID),
    }
    assert observed["idempotency_key"] == f"application_kit:{USER_ID}:job"
    assert not any("COMMIT" in query.upper() for _, query, _ in db.calls)
    assert any("background_job_id" in query for _, query, _ in db.calls)


@pytest.mark.asyncio
async def test_enqueue_reuses_an_active_owned_operation_without_creating_a_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = ScriptedConnection(fetchrows=[None, _operation_row(status="running")])

    async def unexpected_enqueue(*args: object, **kwargs: object) -> uuid.UUID:
        raise AssertionError("active operation must not enqueue another job")

    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", unexpected_enqueue)

    response = await ai_operations.enqueue_ai_operation(
        db,  # type: ignore[arg-type]
        user_id=USER_ID,
        kind="application_kit",
        payload={},
        idempotency_key=f"application_kit:{USER_ID}:job",
    )

    assert response.status == "running"


@pytest.mark.asyncio
async def test_running_and_success_transitions_are_atomic_and_guarded() -> None:
    running = _operation_row(
        status="running", progress_percent=1, stage="starting", message="Starting work."
    )
    succeeded = _operation_row(
        status="succeeded",
        progress_percent=100,
        stage="ready",
        message="Your application kit is ready.",
        result_type="application_kit",
        result_id=uuid.uuid4(),
        completed_at=NOW,
    )
    db = ScriptedConnection(fetchrows=[running, succeeded])

    started = await ai_operations.mark_operation_running(
        db,
        OPERATION_ID,
        stage="starting",
        message="Starting work.",  # type: ignore[arg-type]
    )
    finished = await ai_operations.mark_operation_succeeded(
        db,  # type: ignore[arg-type]
        OPERATION_ID,
        result_type="application_kit",
        result_id=succeeded["result_id"],  # type: ignore[arg-type]
        message="Your application kit is ready.",
    )

    assert started is not None and started.status == "running"
    assert finished is not None and finished.status == "succeeded"
    running_sql = db.calls[0][1]
    success_sql = db.calls[1][1]
    assert "status = 'queued'" in running_sql
    assert "status = 'running'" in success_sql
    assert "progress_percent = 100" in success_sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result_type", "result_id"),
    [
        (None, None),
        ("application_kit", None),
        (None, uuid.uuid4()),
        ("   ", uuid.uuid4()),
    ],
)
async def test_success_rejects_missing_or_partial_result_references(
    result_type: str | None,
    result_id: uuid.UUID | None,
) -> None:
    db = ScriptedConnection()

    with pytest.raises(ai_operations.AiOperationLifecycleError):
        await ai_operations.mark_operation_succeeded(
            db,  # type: ignore[arg-type]
            OPERATION_ID,
            result_type=result_type,
            result_id=result_id,
        )

    assert db.calls == []


@pytest.mark.asyncio
async def test_success_allows_explicitly_resultless_operation() -> None:
    succeeded = _operation_row(
        status="succeeded",
        progress_percent=100,
        stage="ready",
        message="Maintenance is complete.",
        completed_at=NOW,
    )
    db = ScriptedConnection(fetchrows=[succeeded])

    response = await ai_operations.mark_operation_succeeded(
        db,  # type: ignore[arg-type]
        OPERATION_ID,
        message="Maintenance is complete.",
        allow_resultless=True,
    )

    assert response is not None and response.status == "succeeded"


@pytest.mark.asyncio
async def test_progress_update_enforces_monotonicity_at_the_sql_boundary() -> None:
    db = ScriptedConnection(fetchrows=[None])

    updated = await ai_operations.update_operation_progress(
        db,  # type: ignore[arg-type]
        OPERATION_ID,
        20,
        "generating",
        "Generating your application kit.",
    )

    assert updated is None
    sql = db.calls[0][1]
    assert "status = 'running'" in sql
    assert "$2 >= progress_percent" in sql
    assert "BETWEEN 0 AND 99" in sql


@pytest.mark.asyncio
async def test_terminal_operations_cannot_be_mutated() -> None:
    db = ScriptedConnection(fetchrows=[None, None, None])

    assert await ai_operations.mark_operation_running(db, OPERATION_ID) is None  # type: ignore[arg-type]
    assert (
        await ai_operations.update_operation_progress(
            db,
            OPERATION_ID,
            90,
            "saving",
            "Saving your result.",  # type: ignore[arg-type]
        )
        is None
    )
    assert (
        await ai_operations.mark_operation_succeeded(
            db,  # type: ignore[arg-type]
            OPERATION_ID,
            result_type="application_kit",
            result_id=uuid.uuid4(),
        )
        is None
    )
    assert all(
        "status = 'queued'" in query or "status = 'running'" in query
        for method, query, _ in db.calls
        if method == "fetchrow"
    )


@pytest.mark.asyncio
async def test_failure_persists_only_safe_operation_error_and_raw_queue_error() -> None:
    failed = _operation_row(
        status="failed",
        error_code="provider_timeout",
        error_message="The AI provider took too long to respond. Please try again.",
        completed_at=NOW,
    )
    db = ScriptedConnection(fetchrows=[failed])
    raw = TimeoutError("Bearer secret-provider-token")

    response = await ai_operations.mark_operation_failed(
        db,
        OPERATION_ID,
        raw,  # type: ignore[arg-type]
    )

    assert response is not None
    assert response.error_code == "provider_timeout"
    operation_args = db.calls[0][2]
    queue_args = db.calls[1][2]
    assert str(raw) not in operation_args
    assert str(raw) in queue_args
    assert "background_jobs" in db.calls[1][1]


@pytest.mark.asyncio
async def test_cancel_checks_owner_and_cancels_linked_active_queue_job() -> None:
    cancelled = _operation_row(status="cancelled", completed_at=NOW)
    db = ScriptedConnection(fetchrows=[cancelled])

    response = await ai_operations.cancel_owned_operation(
        db,
        OPERATION_ID,
        USER_ID,  # type: ignore[arg-type]
    )

    assert response.status == "cancelled"
    assert "user_id = $2" in db.calls[0][1]
    assert "status IN ('queued', 'running')" in db.calls[0][1]
    assert "background_jobs" in db.calls[1][1]


@pytest.mark.asyncio
async def test_retry_requires_owned_retryable_failure_and_reuses_private_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_payload = {"candidate_id": str(uuid.uuid4()), "operation_id": str(OPERATION_ID)}
    retry_row = {
        "id": OPERATION_ID,
        "kind": "application_kit",
        "candidate_id": uuid.uuid4(),
        "recruiter_id": None,
        "resource_type": "job",
        "resource_id": uuid.uuid4(),
        "idempotency_key": f"application_kit:{USER_ID}:job",
        "error_code": "provider_timeout",
        "expires_at": NOW + timedelta(hours=1),
        "payload": old_payload,
        "max_attempts": 3,
    }
    db = ScriptedConnection(fetchrows=[retry_row])
    observed: dict[str, Any] = {}
    retried = AiOperationResponse.model_validate(_operation_row(id=uuid.uuid4(), status="queued"))

    async def fake_enqueue(db_arg: object, **kwargs: object) -> AiOperationResponse:
        observed["db"] = db_arg
        observed.update(kwargs)
        return retried

    monkeypatch.setattr(ai_operations, "enqueue_ai_operation", fake_enqueue)

    response = await ai_operations.retry_owned_operation(
        db,
        OPERATION_ID,
        USER_ID,
        now=NOW,  # type: ignore[arg-type]
    )

    assert response.id == retried.id
    assert observed["retry_of"] == OPERATION_ID
    assert observed["payload"] == {"candidate_id": old_payload["candidate_id"]}
    assert observed["db"] is db


@pytest.mark.asyncio
async def test_retry_rejects_non_retryable_failure() -> None:
    db = ScriptedConnection(
        fetchrows=[
            {
                "id": OPERATION_ID,
                "error_code": "invalid_input",
                "expires_at": None,
                "payload": {},
            }
        ]
    )

    with pytest.raises(ai_operations.AiOperationLifecycleError):
        await ai_operations.retry_owned_operation(
            db,
            OPERATION_ID,
            USER_ID,
            now=NOW,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_retry_rejects_missing_background_job() -> None:
    db = ScriptedConnection(fetchrows=[None], fetchvals=["failed"])

    with pytest.raises(ai_operations.AiOperationLifecycleError):
        await ai_operations.retry_owned_operation(
            db,
            OPERATION_ID,
            USER_ID,
            now=NOW,  # type: ignore[arg-type]
        )

    retry_query = db.calls[0][1]
    assert "JOIN public.background_jobs" in retry_query
    assert "j.payload IS NOT NULL" in retry_query


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, [], "{malformed json"])
async def test_retry_rejects_missing_non_object_or_malformed_payload(payload: object) -> None:
    retry_row = {
        "id": OPERATION_ID,
        "kind": "application_kit",
        "candidate_id": uuid.uuid4(),
        "recruiter_id": None,
        "resource_type": "job",
        "resource_id": uuid.uuid4(),
        "idempotency_key": f"application_kit:{USER_ID}:job",
        "error_code": "provider_timeout",
        "expires_at": NOW + timedelta(hours=1),
        "payload": payload,
        "max_attempts": 3,
    }
    db = ScriptedConnection(fetchrows=[retry_row])

    with pytest.raises(ai_operations.AiOperationLifecycleError):
        await ai_operations.retry_owned_operation(
            db,
            OPERATION_ID,
            USER_ID,
            now=NOW,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_owned_reads_filter_soft_deleted_rows_and_project_safe_columns() -> None:
    db = ScriptedConnection(
        fetchrows=[_operation_row()], fetch_result=[_operation_row(status="running")]
    )

    one = await ai_operations.get_owned_operation(db, OPERATION_ID, USER_ID)  # type: ignore[arg-type]
    active = await ai_operations.list_owned_operations(db, USER_ID)  # type: ignore[arg-type]

    assert one is not None
    assert active[0].status == "running"
    for _, query, _ in db.calls:
        assert "deleted_at IS NULL" in query
        assert "payload" not in query
        assert "last_error" not in query
        assert "SELECT *" not in query.upper()
