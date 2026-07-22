from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from unittest.mock import ANY, AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.main import app
from hireloop_api.models.ai_operation import AiOperationResponse
from hireloop_api.services import ai_operations, rate_limit

USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OPERATION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


class _Transaction(AbstractAsyncContextManager[None]):
    def __init__(self, db: _FakeDb) -> None:
        self.db = db

    async def __aenter__(self) -> None:
        self.db.transactions_started += 1

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.db.transactions_finished += 1


class _FakeDb:
    def __init__(self) -> None:
        self.transactions_started = 0
        self.transactions_finished = 0

    def transaction(self) -> _Transaction:
        return _Transaction(self)


def _operation(
    *,
    operation_id: uuid.UUID = OPERATION_ID,
    status: str = "running",
    error_code: str | None = None,
) -> AiOperationResponse:
    now = datetime.now(UTC)
    return AiOperationResponse.model_validate(
        {
            "id": operation_id,
            "kind": "career_path_generate",
            "status": status,
            "progress_percent": 25 if status == "running" else 0,
            "stage": "generating",
            "message": "Generating your career path.",
            "error_code": error_code,
            "retryable": error_code == "provider_timeout",
            "created_at": now,
            "updated_at": now,
            "completed_at": now if status in {"failed", "cancelled", "succeeded"} else None,
        }
    )


@pytest.fixture
async def route_client() -> tuple[AsyncClient, _FakeDb]:
    db = _FakeDb()

    async def _user() -> dict[str, object]:
        return {"id": str(USER_ID), "role": "candidate", "phone_verified": True}

    async def _db() -> AsyncIterator[_FakeDb]:
        yield db

    app.dependency_overrides[get_phone_verified_user] = _user
    app.dependency_overrides[get_db] = _db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_owned_operation_returns_safe_projection(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = route_client
    get_owned = AsyncMock(return_value=_operation())
    monkeypatch.setattr(ai_operations, "get_owned_operation", get_owned)

    response = await client.get(f"/api/v1/ai-operations/{OPERATION_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == str(OPERATION_ID)
    assert "background_job_id" not in response.json()
    assert "payload" not in response.json()
    get_owned.assert_awaited_once_with(ANY, OPERATION_ID, USER_ID)


@pytest.mark.asyncio
async def test_missing_or_non_owned_operation_returns_404(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = route_client
    monkeypatch.setattr(ai_operations, "get_owned_operation", AsyncMock(return_value=None))

    response = await client.get(f"/api/v1/ai-operations/{OPERATION_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "AI operation not found"}


@pytest.mark.asyncio
async def test_list_active_operations_is_owned_and_active_only(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = route_client
    list_owned = AsyncMock(return_value=[_operation()])
    monkeypatch.setattr(ai_operations, "list_owned_operations", list_owned)

    response = await client.get("/api/v1/ai-operations?status=active")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(OPERATION_ID)]
    list_owned.assert_awaited_once_with(ANY, USER_ID, active_only=True, limit=50)


@pytest.mark.asyncio
async def test_cancel_owned_operation_uses_a_transaction(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = route_client
    cancel_owned = AsyncMock(return_value=_operation(status="cancelled", error_code="cancelled"))
    monkeypatch.setattr(ai_operations, "cancel_owned_operation", cancel_owned)

    response = await client.post(f"/api/v1/ai-operations/{OPERATION_ID}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert db.transactions_started == db.transactions_finished == 1
    cancel_owned.assert_awaited_once_with(db, OPERATION_ID, USER_ID)


@pytest.mark.asyncio
async def test_terminal_cancel_returns_409(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = route_client
    monkeypatch.setattr(
        ai_operations,
        "cancel_owned_operation",
        AsyncMock(
            side_effect=ai_operations.AiOperationLifecycleError(
                "queue payload diagnostic: provider-secret"
            )
        ),
    )

    response = await client.post(f"/api/v1/ai-operations/{OPERATION_ID}/cancel")

    assert response.status_code == 409
    assert response.json() == {"detail": "This operation can no longer be cancelled."}
    assert "queue payload diagnostic" not in response.text
    assert "provider-secret" not in response.text


@pytest.mark.asyncio
async def test_retry_owned_operation_uses_a_transaction(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = route_client
    retry_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    get_owned = AsyncMock(return_value=_operation(status="failed", error_code="provider_timeout"))
    retry_owned = AsyncMock(return_value=_operation(operation_id=retry_id, status="queued"))
    check_retry_rate = AsyncMock(return_value=None)
    monkeypatch.setattr(ai_operations, "get_owned_operation", get_owned)
    monkeypatch.setattr(ai_operations, "retry_owned_operation", retry_owned)
    monkeypatch.setattr(rate_limit, "check_rate_limit", check_retry_rate)

    response = await client.post(f"/api/v1/ai-operations/{OPERATION_ID}/retry")

    assert response.status_code == 200
    assert response.json()["id"] == str(retry_id)
    assert db.transactions_started == db.transactions_finished == 1
    get_owned.assert_awaited_once_with(db, OPERATION_ID, USER_ID)
    check_retry_rate.assert_awaited_once_with(
        str(USER_ID),
        "ai_operation_retry:career_path_generate",
        max_per_hour=5,
        db=db,
    )
    retry_owned.assert_awaited_once_with(db, OPERATION_ID, USER_ID)


@pytest.mark.asyncio
async def test_non_retryable_failure_returns_409(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = route_client
    monkeypatch.setattr(
        ai_operations,
        "get_owned_operation",
        AsyncMock(return_value=_operation(status="failed", error_code="invalid_input")),
    )
    monkeypatch.setattr(rate_limit, "check_rate_limit", AsyncMock(return_value=None))
    monkeypatch.setattr(
        ai_operations,
        "retry_owned_operation",
        AsyncMock(
            side_effect=ai_operations.AiOperationLifecycleError(
                "background job payload missing: internal-secret"
            )
        ),
    )

    response = await client.post(f"/api/v1/ai-operations/{OPERATION_ID}/retry")

    assert response.status_code == 409
    assert response.json() == {"detail": "This operation cannot be retried."}
    assert "background job payload" not in response.text
    assert "internal-secret" not in response.text


@pytest.mark.asyncio
async def test_retry_rate_limit_preserves_429_and_does_not_enqueue(
    route_client: tuple[AsyncClient, _FakeDb], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = route_client
    get_owned = AsyncMock(return_value=_operation(status="failed", error_code="provider_timeout"))
    retry_owned = AsyncMock()
    check_retry_rate = AsyncMock(
        side_effect=HTTPException(
            status_code=429,
            detail="Retry limit reached.",
            headers={"Retry-After": "900"},
        )
    )
    monkeypatch.setattr(ai_operations, "get_owned_operation", get_owned)
    monkeypatch.setattr(ai_operations, "retry_owned_operation", retry_owned)
    monkeypatch.setattr(rate_limit, "check_rate_limit", check_retry_rate)

    response = await client.post(f"/api/v1/ai-operations/{OPERATION_ID}/retry")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"
    assert db.transactions_started == db.transactions_finished == 1
    get_owned.assert_awaited_once_with(db, OPERATION_ID, USER_ID)
    retry_owned.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "retry"])
async def test_non_owned_mutation_returns_404(
    action: str,
    route_client: tuple[AsyncClient, _FakeDb],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = route_client
    retry_rate = AsyncMock(return_value=None)
    monkeypatch.setattr(
        ai_operations,
        f"{action}_owned_operation",
        AsyncMock(side_effect=ai_operations.AiOperationNotFoundError("hidden")),
    )
    if action == "retry":
        monkeypatch.setattr(ai_operations, "get_owned_operation", AsyncMock(return_value=None))
        monkeypatch.setattr(rate_limit, "check_rate_limit", retry_rate)

    response = await client.post(f"/api/v1/ai-operations/{OPERATION_ID}/{action}")

    assert response.status_code == 404
    assert response.json() == {"detail": "AI operation not found"}
    if action == "retry":
        retry_rate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/ai-operations/not-a-uuid"),
        ("POST", "/api/v1/ai-operations/not-a-uuid/cancel"),
        ("POST", "/api/v1/ai-operations/not-a-uuid/retry"),
    ],
)
async def test_malformed_operation_uuid_is_indistinguishable_from_missing(
    method: str,
    path: str,
    route_client: tuple[AsyncClient, _FakeDb],
) -> None:
    client, _ = route_client

    response = await client.request(method, path)

    assert response.status_code == 404
    assert response.json() == {"detail": "AI operation not found"}
