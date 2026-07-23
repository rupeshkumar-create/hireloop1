"""Tests for tailored resume opt-in setting and queued generation contracts."""

from __future__ import annotations

import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from hireloop_api.models.ai_operation import AiOperationResponse
from hireloop_api.routes import tailored_resumes
from hireloop_api.services.tailored_resume_settings import tailored_resume_enabled


def test_tailored_resume_disabled_by_default() -> None:
    assert tailored_resume_enabled({}) is False
    assert tailored_resume_enabled({"tailored_resume_enabled": False}) is False


def test_tailored_resume_enabled_when_opted_in() -> None:
    assert tailored_resume_enabled({"tailored_resume_enabled": True}) is True


class _Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _TailorDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.resume_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.candidates" in query:
            return {"id": self.candidate_id, "tailored_resume_enabled": True}
        if "FROM public.tailored_resumes" in query and "status = 'ready'" in query:
            return None
        if "INSERT INTO public.tailored_resumes" in query:
            return {"id": self.resume_id, "status": "processing"}
        if "SELECT id, status, expires_at FROM public.tailored_resumes" in query:
            return {"id": self.resume_id, "status": "processing", "expires_at": None}
        return None

    async def execute(self, query: str, *args: object) -> str:
        return "UPDATE 1"


def _operation(
    *, operation_id: uuid.UUID | None = None, status: str = "queued"
) -> AiOperationResponse:
    now = datetime.now(UTC)
    return AiOperationResponse.model_validate(
        {
            "id": operation_id or uuid.uuid4(),
            "kind": "tailored_resume",
            "status": status,
            "progress_percent": 0,
            "stage": "queued",
            "message": "Your tailored resume is queued.",
            "created_at": now,
            "updated_at": now,
        }
    )


@pytest.mark.asyncio
async def test_tailored_resume_submission_returns_ai_operation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _TailorDb()
    queued = _operation()
    enqueue = AsyncMock(return_value=SimpleNamespace(operation=queued, created=True))
    monkeypatch.setattr("hireloop_api.services.ai_operations.enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(tailored_resumes, "check_rate_limit", AsyncMock(return_value=None))

    response = Response()
    out = await tailored_resumes.request_tailored_resume(
        body=tailored_resumes.TailorRequest(job_id=db.job_id, template="modern"),
        response=response,
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert response.status_code == 202
    assert out.operation_id == queued.id
    assert out.status == "queued"
    assert out.status_url == f"/api/v1/ai-operations/{queued.id}"
    assert out.retry_after_ms == 1500
    assert enqueue.await_args.kwargs["kind"] == "tailored_resume"
    assert enqueue.await_args.kwargs["idempotency_key"] == (
        f"tailored_resume:{db.candidate_id}:{db.job_id}"
    )
    assert enqueue.await_args.kwargs["resource_id"] == db.resume_id


@pytest.mark.asyncio
async def test_tailored_resume_duplicate_reuses_active_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _TailorDb()
    queued = _operation(status="running")
    enqueue = AsyncMock(return_value=SimpleNamespace(operation=queued, created=False))
    rate_limit = AsyncMock(return_value=None)
    monkeypatch.setattr("hireloop_api.services.ai_operations.enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(tailored_resumes, "check_rate_limit", rate_limit)

    user = {"id": str(uuid.uuid4())}
    first = await tailored_resumes.request_tailored_resume(
        body=tailored_resumes.TailorRequest(job_id=db.job_id),
        response=Response(),
        current_user=user,
        db=db,  # type: ignore[arg-type]
    )
    second = await tailored_resumes.request_tailored_resume(
        body=tailored_resumes.TailorRequest(job_id=db.job_id),
        response=Response(),
        current_user=user,
        db=db,  # type: ignore[arg-type]
    )

    assert first.operation_id == second.operation_id == queued.id
    assert first.status_url == second.status_url
    assert first.retry_after_ms == second.retry_after_ms == 1500
    assert enqueue.await_count == 2
    rate_limit.assert_not_awaited()


class _ExpiredReadyTailorDb(_TailorDb):
    def __init__(self) -> None:
        super().__init__()
        self.updates: list[tuple[str, tuple[object, ...]]] = []
        self.expired_at = datetime(2020, 1, 1, tzinfo=UTC)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.candidates" in query:
            return {"id": self.candidate_id, "tailored_resume_enabled": True}
        if "FROM public.tailored_resumes" in query and "expires_at > NOW()" in query:
            return None
        if "INSERT INTO public.tailored_resumes" in query:
            return None
        if "SELECT id, status, expires_at FROM public.tailored_resumes" in query:
            return {
                "id": self.resume_id,
                "status": "ready",
                "expires_at": self.expired_at,
            }
        return None

    async def execute(self, query: str, *args: object) -> str:
        self.updates.append((query, args))
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_expired_ready_tailored_resume_flips_to_processing_on_regenerate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _ExpiredReadyTailorDb()
    queued = _operation()
    enqueue = AsyncMock(return_value=SimpleNamespace(operation=queued, created=True))
    monkeypatch.setattr("hireloop_api.services.ai_operations.enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(tailored_resumes, "check_rate_limit", AsyncMock(return_value=None))

    response = Response()
    out = await tailored_resumes.request_tailored_resume(
        body=tailored_resumes.TailorRequest(job_id=db.job_id, template="classic"),
        response=response,
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert response.status_code == 202
    assert out.operation_id == queued.id
    assert len(db.updates) == 1
    update_query, update_args = db.updates[0]
    assert "SET status = 'processing'" in update_query
    assert "status <> 'ready'" not in update_query
    assert update_args == (db.candidate_id, db.job_id, "classic")
