from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from hireloop_api.config import Settings
from hireloop_api.routes import application_kits


class _PrepareDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.saved = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.candidates" in query:
            return {"id": self.candidate_id}
        if "FROM public.jobs" in query:
            return {"id": self.job_id}
        if "FROM public.job_application_kits" in query:
            return None
        return None

    async def execute(self, query: str, *args: object) -> str:
        if "INSERT INTO public.saved_jobs" in query:
            self.saved = True
        return "INSERT 0 1"


class _ExistingMissingResumeDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.kit_id = uuid.uuid4()
        self.enqueued = False
        self.active_job_id: uuid.UUID | None = None

    def _kit_row(self) -> dict[str, object]:
        now = datetime.now(UTC)
        return {
            "id": self.kit_id,
            "job_id": self.job_id,
            "job_title": "Growth Lead",
            "company_name": "Acme",
            "cover_letter": "Dear Hiring Team...",
            "interview_prep": "## Likely questions",
            "tailored_resume_id": None,
            "mock_interview_id": None,
            "created_at": now,
            "updated_at": now,
        }

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.candidates" in query:
            return {"id": self.candidate_id}
        if "FROM public.background_jobs" in query:
            if not self.active_job_id:
                return None
            now = datetime.now(UTC)
            return {
                "id": self.active_job_id,
                "status": "running",
                "last_error": None,
                "attempts": 1,
                "max_attempts": 3,
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
            }
        if "FROM public.job_application_kits" in query:
            return self._kit_row()
        return None

    async def fetchval(self, query: str, *args: object) -> object:
        return self.active_job_id


async def test_prepare_application_kit_route_enqueues_background_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _PrepareDb()
    enqueued: dict[str, object] = {}

    async def _fake_enqueue(db_arg: object, **kwargs: object) -> uuid.UUID:
        enqueued.update(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", _fake_enqueue)

    out = await application_kits.prepare_application_kit_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, environment="test"),  # type: ignore[call-arg]
    )

    assert out["status"] == "processing"
    assert out["saved"] is True
    assert db.saved is True
    assert enqueued["kind"] == "application_kit"
    assert enqueued["payload"] == {
        "candidate_id": str(db.candidate_id),
        "job_id": str(db.job_id),
    }


async def test_prepare_existing_kit_without_resume_requeues_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _ExistingMissingResumeDb()
    enqueued: dict[str, object] = {}
    background_job_id = uuid.uuid4()

    async def _fake_enqueue(db_arg: object, **kwargs: object) -> uuid.UUID:
        enqueued.update(kwargs)
        return background_job_id

    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", _fake_enqueue)

    out = await application_kits.prepare_application_kit_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, environment="test"),  # type: ignore[call-arg]
    )

    assert out == {
        "status": "processing",
        "saved": True,
        "job_id": str(db.job_id),
        "background_job_id": str(background_job_id),
        "message": "Preparing your tailored resume.",
    }
    assert enqueued["kind"] == "application_kit"
    assert enqueued["idempotency_key"] == f"application_kit:{db.candidate_id}:{db.job_id}"


async def test_get_existing_kit_without_resume_stays_not_ready_while_job_active() -> None:
    db = _ExistingMissingResumeDb()
    db.active_job_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await application_kits.get_application_kit_for_job(
            str(db.job_id),
            current_user={"id": str(uuid.uuid4())},
            db=db,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Application kit is still preparing"


async def test_status_reports_processing_for_active_background_job() -> None:
    db = _ExistingMissingResumeDb()
    db.active_job_id = uuid.uuid4()

    out = await application_kits.get_application_kit_status_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert out["status"] == "processing"
    assert out["saved"] is True
    assert out["background_job"]["id"] == str(db.active_job_id)


async def test_status_incomplete_kit_without_resume_is_missing_not_ready() -> None:
    db = _ExistingMissingResumeDb()

    out = await application_kits.get_application_kit_status_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    # Cover/prep alone must not stop polling as "ready" — resume is required.
    assert out["status"] == "missing"
    assert out["saved"] is True


async def test_status_returns_ready_only_when_tailored_resume_exists() -> None:
    class _ReadyDb(_ExistingMissingResumeDb):
        def _kit_row(self) -> dict[str, object]:
            row = super()._kit_row()
            row["tailored_resume_id"] = uuid.uuid4()
            return row

    db = _ReadyDb()

    out = await application_kits.get_application_kit_status_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert out["status"] == "ready"
    assert out["saved"] is True
    assert out["kit"]["tailored_resume_id"] is not None
    assert out["kit"]["cover_letter"] == "Dear Hiring Team..."


async def test_status_reports_failed_when_job_completed_without_resume() -> None:
    class _CompletedIncompleteDb(_ExistingMissingResumeDb):
        def __init__(self) -> None:
            super().__init__()
            self.completed_job_id = uuid.uuid4()

        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "FROM public.candidates" in query:
                return {"id": self.candidate_id}
            if "FROM public.background_jobs" in query:
                now = datetime.now(UTC)
                return {
                    "id": self.completed_job_id,
                    "status": "completed",
                    "last_error": None,
                    "attempts": 1,
                    "max_attempts": 3,
                    "created_at": now,
                    "updated_at": now,
                    "completed_at": now,
                }
            if "FROM public.job_application_kits" in query:
                return self._kit_row()
            return None

    db = _CompletedIncompleteDb()

    out = await application_kits.get_application_kit_status_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert out["status"] == "failed"
    assert "resume" in out["message"].lower()


async def test_status_reports_failed_background_job_without_assets() -> None:
    class _FailedDb(_ExistingMissingResumeDb):
        def __init__(self) -> None:
            super().__init__()
            self.failed_job_id = uuid.uuid4()

        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "FROM public.candidates" in query:
                return {"id": self.candidate_id}
            if "FROM public.background_jobs" in query:
                now = datetime.now(UTC)
                return {
                    "id": self.failed_job_id,
                    "status": "failed",
                    "last_error": "boom",
                    "attempts": 3,
                    "max_attempts": 3,
                    "created_at": now,
                    "updated_at": now,
                    "completed_at": now,
                }
            if "FROM public.job_application_kits" in query:
                return None
            return None

    db = _FailedDb()

    out = await application_kits.get_application_kit_status_for_job(
        str(db.job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert out["status"] == "failed"
    assert out["saved"] is False
    assert out["background_job"]["status"] == "failed"
    assert "Please retry" in out["message"]
