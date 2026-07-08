from __future__ import annotations

import uuid

import pytest

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
