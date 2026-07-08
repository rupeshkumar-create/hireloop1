from __future__ import annotations

import uuid

import pytest

from hireloop_api.services.background_jobs import HM_ENRICH
from hireloop_api.services.intro_service import create_candidate_intro


class _Db:
    """Minimal fake asyncpg connection for create_candidate_intro legacy HM flow."""

    def __init__(self) -> None:
        self.company_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()
        self.hm_id: uuid.UUID | None = None
        self.intro_id: uuid.UUID | None = None

    async def fetchrow(self, query: str, *args: object):  # type: ignore[no-untyped-def]
        if "FROM public.candidates" in query and "JOIN public.users" in query:
            return {
                "id": self.candidate_id,
                "full_name": "Test Candidate",
                "email": "c@example.com",
            }
        if "FROM public.jobs j" in query:
            return {
                "id": self.job_id,
                "title": "Backend Engineer",
                "company_id": self.company_id,
                "recruiter_id": None,
            }
        if "FROM public.hiring_managers" in query and "WHERE company_id" in query:
            return None
        if "FROM public.companies" in query:
            return {"name": "Acme"}
        return None

    async def fetchval(self, query: str, *args: object):  # type: ignore[no-untyped-def]
        # "existing intro" check returns None
        return None

    async def execute(self, query: str, *args: object) -> str:  # type: ignore[no-untyped-def]
        if "INSERT INTO public.hiring_managers" in query:
            self.hm_id = args[0] if isinstance(args[0], uuid.UUID) else uuid.UUID(str(args[0]))
            return "INSERT 0 1"
        if "INSERT INTO public.intro_requests" in query:
            self.intro_id = args[0] if isinstance(args[0], uuid.UUID) else uuid.UUID(str(args[0]))
            return "INSERT 0 1"
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_candidate_intro_enqueues_hm_enrich_when_stub_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        captured.update(kwargs)
        return uuid.uuid4()

    # Ensure settings look configured for the enqueue gate.
    from hireloop_api.config import Settings

    monkeypatch.setattr(
        "hireloop_api.services.intro_service.get_settings",
        lambda: Settings(  # type: ignore[call-arg]
            _env_file=None,
            environment="test",
            apify_token="test-token",
            neverbounce_api_key="test-neverbounce",
        ),
    )
    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", fake_enqueue)

    db = _Db()
    out = await create_candidate_intro(
        db,  # type: ignore[arg-type]
        user_id=str(uuid.uuid4()),
        job_id=str(db.job_id),
        message="Please intro me.",
    )

    assert out.get("direction") == "candidate_to_hm"
    assert db.hm_id is not None
    assert captured.get("kind") == HM_ENRICH
    assert captured.get("payload") == {"hm_id": str(db.hm_id)}
    assert captured.get("idempotency_key") == f"hm_enrich:{db.hm_id}"
