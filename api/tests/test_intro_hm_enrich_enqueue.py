from __future__ import annotations

import uuid

import pytest

from hireloop_api.services.background_jobs import HM_ENRICH, NITYA_INTRO_DRAFT
from hireloop_api.services.intro_service import create_candidate_intro


class _Db:
    """Minimal fake asyncpg connection for create_candidate_intro legacy HM flow."""

    def __init__(self) -> None:
        self.company_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()
        self.hm_id: uuid.UUID | None = None
        self.intro_id: uuid.UUID | None = None
        self.intro_status: str | None = None

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
        if "UPDATE public.intro_requests" in query and "status = 'enriching'" in query:
            self.intro_status = "enriching"
            return "UPDATE 1"
        return "UPDATE 1"


class _ExistingIntroDb(_Db):
    def __init__(self) -> None:
        super().__init__()
        self.hm_id = uuid.uuid4()
        self.existing_intro_id = uuid.uuid4()
        self.draft_backfilled = False

    async def fetchrow(self, query: str, *args: object):  # type: ignore[no-untyped-def]
        if "SELECT id FROM public.hiring_managers" in query and "WHERE company_id" in query:
            return {"id": self.hm_id}
        return await super().fetchrow(query, *args)

    async def fetchval(self, query: str, *args: object):  # type: ignore[no-untyped-def]
        if "FROM public.intro_requests" in query:
            return self.existing_intro_id
        return None

    async def execute(self, query: str, *args: object) -> str:  # type: ignore[no-untyped-def]
        if "COALESCE(draft_email" in query:
            self.draft_backfilled = True
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_candidate_intro_enqueues_hm_enrich_when_stub_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []

    async def fake_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        captured.append(dict(kwargs))
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
    assert out.get("status") == "enriching"
    assert out.get("hm_enrich_queued") is True
    assert out.get("hm_enrich_provider") == "apify"
    assert db.hm_id is not None
    assert db.intro_status == "enriching"
    hm_job = next(job for job in captured if job.get("kind") == HM_ENRICH)
    assert hm_job.get("payload") == {"hm_id": str(db.hm_id)}
    assert hm_job.get("idempotency_key") == f"hm_enrich:{db.hm_id}"
    nitya_job = next(job for job in captured if job.get("kind") == NITYA_INTRO_DRAFT)
    assert nitya_job.get("idempotency_key") == f"nitya_intro_draft:{db.intro_id}"


@pytest.mark.asyncio
async def test_candidate_intro_backfills_simple_draft_for_existing_hm_intro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        return uuid.uuid4()

    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", fake_enqueue)
    db = _ExistingIntroDb()

    out = await create_candidate_intro(
        db,  # type: ignore[arg-type]
        user_id=str(uuid.uuid4()),
        job_id=str(db.job_id),
        message="Please intro me.",
    )

    assert out.get("intro_id") == str(db.existing_intro_id)
    assert out.get("direction") == "candidate_to_hm"
    assert db.draft_backfilled is True


def test_aarya_request_intro_tool_only_requires_job_id() -> None:
    from hireloop_api.agents.aarya.agent import TOOL_DEFINITIONS

    request_intro = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "request_intro")

    assert request_intro["function"]["parameters"]["required"] == ["job_id"]


@pytest.mark.asyncio
async def test_create_intro_route_calls_candidate_intro_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hireloop_api.routes import intros as intro_routes

    captured: dict[str, object] = {}
    job_id = uuid.uuid4()

    async def fake_create_candidate_intro(db: object, **kwargs: object) -> dict[str, object]:
        captured["db"] = db
        captured.update(kwargs)
        return {
            "intro_id": "intro-123",
            "status": "pending",
            "direction": "candidate_to_hm",
        }

    monkeypatch.setattr(intro_routes, "create_candidate_intro", fake_create_candidate_intro)

    db = object()
    result = await intro_routes.create_intro(
        intro_routes.CreateIntroRequest(job_id=job_id),
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert result["intro_id"] == "intro-123"
    assert captured["db"] is db
    assert captured["job_id"] == str(job_id)
    assert captured["hiring_manager_id"] is None


@pytest.mark.asyncio
async def test_request_intro_writes_visible_hm_enrich_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hireloop_api.agents.aarya import tools as aarya_tools

    action_types: list[str] = []

    class ActionDb:
        async def execute(self, query: str, *args: object) -> str:  # type: ignore[no-untyped-def]
            if "INSERT INTO public.agent_actions" in query:
                action_types.append(str(args[3]))
            return "INSERT 0 1"

    async def fake_create_candidate_intro(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "intro_id": str(uuid.uuid4()),
            "status": "enriching",
            "direction": "candidate_to_hm",
            "hm_enrich_queued": True,
            "hm_enrich_provider": "apify",
        }

    monkeypatch.setattr(
        "hireloop_api.services.intro_service.create_candidate_intro",
        fake_create_candidate_intro,
    )

    await aarya_tools.request_intro(
        ActionDb(),  # type: ignore[arg-type]
        user_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        job_id=str(uuid.uuid4()),
    )

    assert action_types == ["request_intro", "hm_enrich_queued"]
