"""Tests for career path helpers and durable generation submission."""

from __future__ import annotations

import time
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from hireloop_api import deps
from hireloop_api.models.ai_operation import AiOperationResponse
from hireloop_api.routes import career
from hireloop_api.services import ai_operations, background_jobs
from hireloop_api.services import rate_limit as rate_limit_service
from hireloop_api.services.career_intelligence.engine import PreparedCareerIntelligence
from hireloop_api.services.career_intelligence.schema import CareerIntelligence
from hireloop_api.services.career_path import (
    _build_profile_brief,
    _profile_ready_for_path,
    build_career_path_system_prompt,
    path_from_career_intelligence,
)


class _Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class _Db:
    def transaction(self) -> _Transaction:
        return _Transaction()


class _Acquire(AbstractAsyncContextManager[_Db]):
    def __init__(self, db: _Db) -> None:
        self.db = db

    async def __aenter__(self) -> _Db:
        return self.db

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class _Pool:
    def __init__(self) -> None:
        self.db = _Db()

    def acquire(self) -> _Acquire:
        return _Acquire(self.db)


def _operation(kind: str, *, operation_id: uuid.UUID | None = None) -> AiOperationResponse:
    now = datetime.now(UTC)
    return AiOperationResponse.model_validate(
        {
            "id": operation_id or uuid.uuid4(),
            "kind": kind,
            "status": "queued",
            "progress_percent": 0,
            "stage": "queued",
            "message": "Your request is queued.",
            "created_at": now,
            "updated_at": now,
        }
    )


def _enqueue_outcome(
    operation: AiOperationResponse,
    *,
    created: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(operation=operation, created=created)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("submit", "kind", "latest_attr", "provider_attr"),
    [
        (
            career.generate_career_path,
            "career_path_generate",
            "get_latest",
            "generate",
        ),
        (
            career.generate_career_intelligence,
            "career_intelligence_generate",
            "get",
            "generate",
        ),
    ],
)
async def test_generation_submission_returns_202_without_awaiting_provider(
    monkeypatch: pytest.MonkeyPatch,
    submit: Any,
    kind: str,
    latest_attr: str,
    provider_attr: str,
) -> None:
    pool = _Pool()
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    queued = _operation(kind)
    enqueue = AsyncMock(return_value=_enqueue_outcome(queued))
    provider = AsyncMock(side_effect=AssertionError("provider work ran in request"))
    service = (
        career.CareerPathService
        if kind == "career_path_generate"
        else career.CareerIntelligenceService
    )

    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(service, latest_attr, AsyncMock(return_value=None))
    monkeypatch.setattr(service, provider_attr, provider)
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    rate_limit = AsyncMock(return_value=None)
    monkeypatch.setattr(career, "check_rate_limit", rate_limit)

    response = Response()
    started = time.monotonic()
    result = await submit(
        response=response,
        current_user={"id": str(user_id)},
        settings=SimpleNamespace(),
    )

    assert time.monotonic() - started < 1
    assert response.status_code == 202
    assert result.operation_id == queued.id
    assert result.status == "queued"
    assert result.status_url == f"/api/v1/ai-operations/{queued.id}"
    assert result.retry_after_ms == 1500
    provider.assert_not_awaited()
    assert enqueue.await_args.kwargs["kind"] == kind
    assert enqueue.await_args.kwargs["candidate_id"] == candidate_id
    assert enqueue.await_args.kwargs["payload"] == {"candidate_id": str(candidate_id)}
    if kind == "career_path_generate":
        rate_limit.assert_awaited_once_with(
            str(user_id), "career_path_generate", max_per_hour=10, db=pool.db
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("submit", "service", "latest_attr", "kind"),
    [
        (
            career.generate_career_path,
            career.CareerPathService,
            "get_latest",
            "career_path_generate",
        ),
        (
            career.generate_career_intelligence,
            career.CareerIntelligenceService,
            "get",
            "career_intelligence_generate",
        ),
    ],
)
async def test_long_running_active_generation_reuses_stable_logical_key(
    monkeypatch: pytest.MonkeyPatch,
    submit: Any,
    service: Any,
    latest_attr: str,
    kind: str,
) -> None:
    pool = _Pool()
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    queued = _operation(kind).model_copy(update={"status": "running"})
    keys: list[str] = []

    class _Clock:
        current = datetime(2026, 7, 22, 12, 4, tzinfo=UTC)

        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return cls.current

    async def _enqueue(*_args: object, **kwargs: Any) -> SimpleNamespace:
        keys.append(str(kwargs["idempotency_key"]))
        return _enqueue_outcome(queued, created=False)

    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(service, latest_attr, AsyncMock(return_value=None))
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", _enqueue)
    rate_limit = AsyncMock(return_value=None)
    monkeypatch.setattr(career, "check_rate_limit", rate_limit)
    monkeypatch.setattr(career, "datetime", _Clock)

    first = await submit(
        response=Response(), current_user={"id": str(user_id)}, settings=SimpleNamespace()
    )
    _Clock.current += timedelta(minutes=10)
    second = await submit(
        response=Response(), current_user={"id": str(user_id)}, settings=SimpleNamespace()
    )

    assert first.operation_id == second.operation_id == queued.id
    assert keys[0] == keys[1]
    assert keys[0] == f"{kind}:{candidate_id}"
    rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_recent_career_path_returns_ready_result_without_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool()
    candidate_id = uuid.uuid4()
    recent = {
        "id": str(uuid.uuid4()),
        "current_role": "Engineer",
        "summary": "Ready",
        "steps": [],
        "target_titles": ["Senior Engineer"],
        "target_locations": ["India"],
        "model": "test",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    enqueue = AsyncMock(side_effect=AssertionError("recent result must not enqueue"))
    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(career.CareerPathService, "get_latest", AsyncMock(return_value=recent))
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    rate_limit = AsyncMock(return_value=None)
    monkeypatch.setattr(career, "check_rate_limit", rate_limit)
    response = Response()

    result = await career.generate_career_path(
        response=response,
        current_user={"id": str(uuid.uuid4())},
        settings=SimpleNamespace(),
    )

    assert response.status_code == 200
    assert result == {"path": recent}
    enqueue.assert_not_awaited()
    rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_recent_career_intelligence_returns_ready_result_without_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool()
    recent = {
        "generated_at": datetime.now(UTC).isoformat(),
        "updated_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "data_completeness": 90,
    }
    enqueue = AsyncMock(side_effect=AssertionError("recent result must not enqueue"))
    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(uuid.uuid4())))
    monkeypatch.setattr(career.CareerIntelligenceService, "get", AsyncMock(return_value=recent))
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    response = Response()

    result = await career.generate_career_intelligence(
        response=response,
        current_user={"id": str(uuid.uuid4())},
        settings=SimpleNamespace(),
    )

    assert response.status_code == 200
    assert result == {"intelligence": recent}
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generated_at",
    [
        (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        None,
        "legacy-invalid-timestamp",
    ],
)
async def test_completeness_update_does_not_make_stale_or_legacy_intelligence_recent(
    monkeypatch: pytest.MonkeyPatch,
    generated_at: str | None,
) -> None:
    pool = _Pool()
    candidate_id = uuid.uuid4()
    stale = {
        "generated_at": generated_at,
        # _sync_completeness updates this timestamp without rebuilding intelligence.
        "updated_at": datetime.now(UTC).isoformat(),
        "data_completeness": 95,
    }
    queued = _operation("career_intelligence_generate")
    enqueue = AsyncMock(return_value=_enqueue_outcome(queued))
    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(career.CareerIntelligenceService, "get", AsyncMock(return_value=stale))
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    response = Response()

    result = await career.generate_career_intelligence(
        response=response,
        current_user={"id": str(uuid.uuid4())},
        settings=SimpleNamespace(),
    )

    assert response.status_code == 202
    assert result.operation_id == queued.id
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("submit", "service", "latest_attr", "kind", "result_key", "fresh"),
    [
        (
            career.generate_career_path,
            career.CareerPathService,
            "get_latest",
            "career_path_generate",
            "path",
            {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
            },
        ),
        (
            career.generate_career_intelligence,
            career.CareerIntelligenceService,
            "get",
            "career_intelligence_generate",
            "intelligence",
            {"generated_at": datetime.now(UTC).isoformat()},
        ),
    ],
)
async def test_completion_between_initial_read_and_enqueue_cancels_redundant_operation(
    monkeypatch: pytest.MonkeyPatch,
    submit: Any,
    service: Any,
    latest_attr: str,
    kind: str,
    result_key: str,
    fresh: dict[str, Any],
) -> None:
    pool = _Pool()
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    queued = _operation(kind)
    active = True
    provider = AsyncMock(side_effect=AssertionError("duplicate provider work must not run"))
    latest = AsyncMock(side_effect=[None, fresh])
    enqueue = AsyncMock(return_value=_enqueue_outcome(queued))
    rate_limit = AsyncMock(return_value=None)

    async def _cancel(*_args: object, **_kwargs: object) -> AiOperationResponse:
        nonlocal active
        active = False
        return queued.model_copy(update={"status": "cancelled"})

    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(service, latest_attr, latest)
    monkeypatch.setattr(service, "generate", provider)
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(ai_operations, "cancel_owned_operation", _cancel)
    monkeypatch.setattr(career, "check_rate_limit", rate_limit)
    response = Response()

    result = await submit(
        response=response,
        current_user={"id": str(user_id)},
        settings=SimpleNamespace(),
    )

    assert response.status_code == 200
    assert result == {result_key: fresh}
    assert latest.await_count == 2
    assert active is False
    provider.assert_not_awaited()
    rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_fresh_race_returns_result_when_worker_already_made_operation_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool()
    candidate_id = uuid.uuid4()
    fresh = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
    }
    queued = _operation("career_path_generate")
    rate_limit = AsyncMock(return_value=None)
    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(
        career.CareerPathService,
        "get_latest",
        AsyncMock(side_effect=[None, fresh]),
    )
    monkeypatch.setattr(
        ai_operations,
        "enqueue_ai_operation_outcome",
        AsyncMock(return_value=_enqueue_outcome(queued)),
    )
    monkeypatch.setattr(
        ai_operations,
        "cancel_owned_operation",
        AsyncMock(
            side_effect=ai_operations.AiOperationLifecycleError("operation already succeeded")
        ),
    )
    monkeypatch.setattr(career, "check_rate_limit", rate_limit)
    response = Response()

    result = await career.generate_career_path(
        response=response,
        current_user={"id": str(uuid.uuid4())},
        settings=SimpleNamespace(),
    )

    assert response.status_code == 200
    assert result == {"path": fresh}
    rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_path_operation_rolls_back_when_generation_quota_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RollbackDb(_Db):
        def __init__(self) -> None:
            self.active_operation = False

        def transaction(self) -> AbstractAsyncContextManager[None]:
            db = self

            class _Rollback(AbstractAsyncContextManager[None]):
                async def __aenter__(self) -> None:
                    return None

                async def __aexit__(
                    self,
                    exc_type: type[BaseException] | None,
                    exc_value: BaseException | None,
                    traceback: object,
                ) -> None:
                    if exc_type is not None:
                        db.active_operation = False

            return _Rollback()

    class _RollbackPool(_Pool):
        def __init__(self) -> None:
            self.db = _RollbackDb()

    pool = _RollbackPool()
    candidate_id = uuid.uuid4()
    queued = _operation("career_path_generate")

    async def _enqueue(db: _RollbackDb, **_kwargs: object) -> SimpleNamespace:
        db.active_operation = True
        return _enqueue_outcome(queued)

    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(career.CareerPathService, "get_latest", AsyncMock(return_value=None))
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", _enqueue)
    monkeypatch.setattr(
        career,
        "check_rate_limit",
        AsyncMock(side_effect=HTTPException(status_code=429, detail="quota reached")),
    )

    with pytest.raises(HTTPException) as exc:
        await career.generate_career_path(
            response=Response(),
            current_user={"id": str(uuid.uuid4())},
            settings=SimpleNamespace(),
        )

    assert exc.value.status_code == 429
    assert pool.db.active_operation is False


@pytest.mark.asyncio
async def test_distributed_quota_db_error_falls_back_without_aborting_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NestedDb(_Db):
        def __init__(self) -> None:
            self.aborted = False
            self.depth = 0

        def transaction(self) -> AbstractAsyncContextManager[None]:
            db = self

            class _NestedTransaction(AbstractAsyncContextManager[None]):
                async def __aenter__(self) -> None:
                    db.depth += 1

                async def __aexit__(
                    self,
                    exc_type: type[BaseException] | None,
                    exc_value: BaseException | None,
                    traceback: object,
                ) -> None:
                    db.depth -= 1
                    if exc_type is not None:
                        db.aborted = False

            return _NestedTransaction()

    class _NestedPool(_Pool):
        def __init__(self) -> None:
            self.db = _NestedDb()

    pool = _NestedPool()
    candidate_id = uuid.uuid4()
    queued = _operation("career_path_generate")
    rate_limit_service.reset_rate_limits()

    async def _distributed_failure(db: _NestedDb, **_kwargs: object) -> None:
        db.aborted = True
        raise RuntimeError("rate limit table unavailable")

    monkeypatch.setattr(career, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(career.CareerPathService, "get_latest", AsyncMock(return_value=None))
    monkeypatch.setattr(
        ai_operations,
        "enqueue_ai_operation_outcome",
        AsyncMock(return_value=_enqueue_outcome(queued)),
    )
    monkeypatch.setattr(
        rate_limit_service,
        "check_distributed_rate_limit",
        _distributed_failure,
    )
    monkeypatch.setattr(career, "check_rate_limit", rate_limit_service.check_rate_limit)

    response = Response()
    result = await career.generate_career_path(
        response=response,
        current_user={"id": str(uuid.uuid4())},
        settings=SimpleNamespace(),
    )

    assert response.status_code == 202
    assert result.operation_id == queued.id
    assert pool.db.aborted is False
    assert pool.db.depth == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "service", "result_type"),
    [
        ("_handle_career_path_generate", career.CareerPathService, "career_path"),
        (
            "_handle_career_intelligence_generate",
            career.CareerIntelligenceService,
            "career_intelligence",
        ),
    ],
)
async def test_generation_handler_defers_domain_write_to_completion_transaction(
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
    service: Any,
    result_type: str,
) -> None:
    candidate_id = uuid.uuid4()
    operation_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    prepared = SimpleNamespace(id=artifact_id)
    prepare = AsyncMock(return_value=prepared)
    persist = AsyncMock(return_value=None)
    stages: list[int] = []

    async def _progress(*_args: object, progress_percent: int, **_kwargs: object) -> None:
        stages.append(progress_percent)

    monkeypatch.setattr(service, "prepare", prepare, raising=False)
    monkeypatch.setattr(service, "persist", persist, raising=False)
    monkeypatch.setattr(background_jobs, "publish_operation_progress", _progress)
    monkeypatch.setattr(deps, "get_db_pool", AsyncMock(return_value=_Pool()))

    handler = getattr(background_jobs, handler_name)
    result = await handler(
        SimpleNamespace(),
        {
            "candidate_id": str(candidate_id),
            "operation_id": str(operation_id),
            "_job_lease_token": "worker:lease",
        },
    )

    assert isinstance(result, background_jobs.HandlerResult)
    assert result.result_type == result_type
    assert result.result_id == artifact_id
    assert stages == [10, 35, 80]
    persist.assert_not_awaited()

    completion_db = object()
    await result.persist(completion_db)  # type: ignore[arg-type]
    persist.assert_awaited_once_with(completion_db, str(candidate_id), prepared)


@pytest.mark.asyncio
async def test_intelligence_persist_rejects_missing_candidate_artifact() -> None:
    candidate_id = uuid.uuid4()
    db = AsyncMock()
    db.execute.return_value = "UPDATE 0"
    prepared = PreparedCareerIntelligence(
        id=candidate_id,
        intelligence=CareerIntelligence(),
    )

    with pytest.raises(ValueError, match="Candidate not found"):
        await career.CareerIntelligenceService.persist(db, str(candidate_id), prepared)


def test_profile_ready_with_current_title() -> None:
    assert _profile_ready_for_path({"current_title": "Software Engineer"}) is True


def test_profile_ready_with_skills() -> None:
    assert _profile_ready_for_path({"skills": ["Python"]}) is True


def test_profile_ready_with_real_headline() -> None:
    assert _profile_ready_for_path({"headline": "Backend engineer at Acme"}) is True


def test_profile_not_ready_for_placeholder_headline() -> None:
    assert _profile_ready_for_path({"headline": "New candidate"}) is False


def test_profile_not_ready_when_empty() -> None:
    assert _profile_ready_for_path({}) is False


def test_career_path_prompt_is_india_only() -> None:
    prompt = build_career_path_system_prompt("IN")

    assert "India" in prompt
    assert "Indian job-board titles" in prompt


def test_career_path_prompt_normalises_non_india_to_india() -> None:
    prompt = build_career_path_system_prompt("US")

    assert "India" in prompt
    assert "Indian job-board titles" in prompt
    assert "United States" not in prompt


def test_career_path_prompt_normalises_uk_to_india() -> None:
    prompt = build_career_path_system_prompt("GB")

    assert "India" in prompt
    assert "United Kingdom" not in prompt
    assert "Indian job-board titles" in prompt


def test_career_path_prompt_blocks_generic_team_lead_titles() -> None:
    prompt = build_career_path_system_prompt("IN")

    assert 'Do NOT emit bare generic titles like "Team Lead"' in prompt
    assert "Implementation Team Lead" in prompt


def test_profile_brief_includes_market_and_full_location() -> None:
    brief = _build_profile_brief(
        {
            "full_name": "Candidate",
            "market": "IN",
            "current_title": "Data Analyst",
            "current_company": "Acme",
            "years_experience": 4,
            "location_city": "Bengaluru",
            "location_state": "Karnataka",
            "skills": ["SQL"],
        }
    )

    assert "Market: IN" in brief
    assert "Location: Bengaluru, Karnataka" in brief


def test_path_from_career_intelligence_orders_by_feasibility() -> None:
    profile = {
        "current_title": "Category Team Lead",
        "skills": ["Customer Success", "Leadership"],
    }
    intelligence = {
        "mobility": {
            "adjacent_roles": [
                {
                    "role": "CX Operations Manager",
                    "feasibility_score": 80,
                    "time_required": "3-6 months",
                    "skill_gap": ["Budget ownership"],
                },
                {
                    "role": "Customer Success Manager",
                    "feasibility_score": 85,
                    "time_required": "0-3 months",
                    "skill_gap": ["CRM proficiency"],
                },
            ]
        }
    }

    path = path_from_career_intelligence(profile, intelligence)

    assert path is not None
    assert path["target_titles"][0] == "Customer Success Manager"
    next_steps = [s for s in path["steps"] if s["level"] == "next"]
    assert next_steps[0]["title"] == "Customer Success Manager"
    assert "85% fit" in (next_steps[0]["rationale"] or "")


@pytest.mark.asyncio
async def test_career_path_resume_submission_returns_ai_operation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    queued = _operation("career_path_resumes")
    enqueue = AsyncMock(return_value=_enqueue_outcome(queued))
    db = _Db()

    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(
        "hireloop_api.services.tailored_resume_settings.fetch_tailored_resume_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "hireloop_api.services.career_path_resume.list_path_resumes",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(career, "check_rate_limit", AsyncMock(return_value=None))

    response = Response()
    result = await career.generate_career_path_resumes(
        response=response,
        current_user={"id": str(user_id)},
        settings=SimpleNamespace(),
        db=db,  # type: ignore[arg-type]
    )

    assert response.status_code == 202
    assert result.operation_id == queued.id
    assert result.status == "queued"
    assert result.status_url == f"/api/v1/ai-operations/{queued.id}"
    assert result.retry_after_ms == 1500
    assert enqueue.await_args.kwargs["kind"] == "career_path_resumes"
    assert enqueue.await_args.kwargs["idempotency_key"] == f"career_path_resumes:{candidate_id}"


@pytest.mark.asyncio
async def test_career_path_resume_duplicate_reuses_active_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_id = uuid.uuid4()
    user_id = uuid.uuid4()
    queued = _operation("career_path_resumes", operation_id=uuid.uuid4()).model_copy(
        update={"status": "running"}
    )
    enqueue = AsyncMock(return_value=_enqueue_outcome(queued, created=False))
    rate_limit = AsyncMock(return_value=None)
    db = _Db()

    monkeypatch.setattr(career, "_resolve_candidate_id", AsyncMock(return_value=str(candidate_id)))
    monkeypatch.setattr(
        "hireloop_api.services.tailored_resume_settings.fetch_tailored_resume_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "hireloop_api.services.career_path_resume.list_path_resumes",
        AsyncMock(return_value=[{"status": "processing"}]),
    )
    monkeypatch.setattr(ai_operations, "enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(career, "check_rate_limit", rate_limit)

    first = await career.generate_career_path_resumes(
        response=Response(),
        current_user={"id": str(user_id)},
        settings=SimpleNamespace(),
        db=db,  # type: ignore[arg-type]
    )
    second = await career.generate_career_path_resumes(
        response=Response(),
        current_user={"id": str(user_id)},
        settings=SimpleNamespace(),
        db=db,  # type: ignore[arg-type]
    )

    assert first.operation_id == second.operation_id == queued.id
    assert first.status_url == second.status_url
    assert first.retry_after_ms == second.retry_after_ms == 1500
    rate_limit.assert_not_awaited()
