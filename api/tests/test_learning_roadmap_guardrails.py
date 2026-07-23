from __future__ import annotations

import json
import uuid
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from langchain_core.messages import AIMessage

from hireloop_api.config import Settings
from hireloop_api.models.ai_operation import AiOperationResponse
from hireloop_api.routes import learning_roadmaps
from hireloop_api.services.learning_roadmap import generate_roadmap, render_roadmap_html


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=self.content)


def _profile() -> dict[str, Any]:
    return {
        "full_name": "Asha Rao",
        "current_title": "Growth Manager",
        "skills": ["SQL", "Lifecycle Marketing"],
        "career_goals": {"desired_title": "Head of Growth"},
    }


def _job() -> dict[str, Any]:
    return {
        "title": "Head of Growth",
        "company_name": "Modern SaaS",
        "skills_required": ["SQL", "Experimentation"],
        "description": "Own growth experiments and lifecycle strategy.",
    }


@pytest.mark.asyncio
async def test_learning_roadmap_repairs_placeholder_llm_json() -> None:
    roadmap = await generate_roadmap(
        llm=_FakeLLM(
            json.dumps(
                {
                    "summary": "null",
                    "target_role": "undefined",
                    "current_strengths": ["SQL", "null"],
                    "gaps": ["undefined"],
                    "phases": [],
                    "stretch_goals": ["none"],
                }
            )
        ),  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job=_job(),
    )

    assert roadmap["summary"] != "null"
    assert roadmap["target_role"] == "Head of Growth"
    assert roadmap["current_strengths"] == ["SQL", "Lifecycle Marketing"]
    assert roadmap["gaps"] == ["Experimentation"]
    assert len(roadmap["phases"]) >= 3
    assert all(phase["milestones"] for phase in roadmap["phases"])

    html = render_roadmap_html(
        roadmap,
        job_title="Head of Growth",
        company_name="Modern SaaS",
        candidate_name="Asha Rao",
        storage_key="roadmap-test",
    )
    assert "No phases generated" not in html
    assert "null" not in html.lower()
    assert "undefined" not in html.lower()


@pytest.mark.asyncio
async def test_learning_roadmap_preserves_useful_llm_phases() -> None:
    roadmap = await generate_roadmap(
        llm=_FakeLLM(
            json.dumps(
                {
                    "summary": "A practical plan for growth leadership.",
                    "target_role": "Head of Growth",
                    "current_strengths": ["SQL"],
                    "gaps": ["Experimentation"],
                    "phases": [
                        {
                            "title": "Phase 1: Growth analytics",
                            "duration": "Weeks 1-2",
                            "focus": "Deepen SQL-driven funnel analysis.",
                            "milestones": ["Audit one lifecycle funnel."],
                            "skills": ["SQL", "Lifecycle Marketing"],
                            "resources": [{"label": "SQL practice", "note": "Use real funnels."}],
                        },
                        {
                            "title": "Phase 2: Experiment design",
                            "duration": "Weeks 3-4",
                            "focus": "Design and score experiments.",
                            "milestones": ["Write three experiment briefs."],
                            "skills": ["Experimentation"],
                            "resources": [],
                        },
                        {
                            "title": "Phase 3: Leadership capstone",
                            "duration": "Weeks 5-6",
                            "focus": "Package a growth strategy.",
                            "milestones": ["Build a 90-day growth plan."],
                            "skills": ["Growth Strategy"],
                            "resources": [],
                        },
                    ],
                    "stretch_goals": ["Create a growth portfolio."],
                }
            )
        ),  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job=_job(),
    )

    assert roadmap["summary"] == "A practical plan for growth leadership."
    assert [phase["title"] for phase in roadmap["phases"]] == [
        "Phase 1: Growth analytics",
        "Phase 2: Experiment design",
        "Phase 3: Leadership capstone",
    ]
    assert roadmap["phases"][0]["milestones"] == ["Audit one lifecycle funnel."]
    assert roadmap["stretch_goals"] == ["Create a growth portfolio."]


class _Transaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _RoadmapDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.roadmap_id = uuid.uuid4()
        self.job_id = uuid.uuid4()

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.candidates" in query:
            return {"id": self.candidate_id}
        if "FROM public.learning_roadmaps" in query and "status = 'ready'" in query:
            return None
        if "INSERT INTO public.learning_roadmaps" in query:
            return {"id": self.roadmap_id, "status": "processing"}
        if "SELECT id, status, expires_at FROM public.learning_roadmaps" in query:
            return {"id": self.roadmap_id, "status": "processing", "expires_at": None}
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
            "kind": "learning_roadmap",
            "status": status,
            "progress_percent": 0,
            "stage": "queued",
            "message": "Your learning roadmap is queued.",
            "created_at": now,
            "updated_at": now,
        }
    )


@pytest.mark.asyncio
async def test_learning_roadmap_submission_returns_ai_operation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _RoadmapDb()
    queued = _operation()
    enqueue = AsyncMock(return_value=SimpleNamespace(operation=queued, created=True))
    monkeypatch.setattr("hireloop_api.services.ai_operations.enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(learning_roadmaps, "check_rate_limit", AsyncMock(return_value=None))

    response = Response()
    out = await learning_roadmaps.request_learning_roadmap(
        body=learning_roadmaps.RoadmapRequest(job_id=db.job_id),
        response=response,
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
        settings=Settings(_env_file=None, environment="test"),  # type: ignore[call-arg]
    )

    assert response.status_code == 202
    assert out.operation_id == queued.id
    assert out.status_url == f"/api/v1/ai-operations/{queued.id}"
    assert out.retry_after_ms == 1500
    assert enqueue.await_args.kwargs["kind"] == "learning_roadmap"
    assert enqueue.await_args.kwargs["resource_id"] == db.roadmap_id


@pytest.mark.asyncio
async def test_learning_roadmap_duplicate_reuses_active_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _RoadmapDb()
    queued = _operation(status="running")
    enqueue = AsyncMock(return_value=SimpleNamespace(operation=queued, created=False))
    rate_limit = AsyncMock(return_value=None)
    monkeypatch.setattr("hireloop_api.services.ai_operations.enqueue_ai_operation_outcome", enqueue)
    monkeypatch.setattr(learning_roadmaps, "check_rate_limit", rate_limit)

    user = {"id": str(uuid.uuid4())}
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    first = await learning_roadmaps.request_learning_roadmap(
        body=learning_roadmaps.RoadmapRequest(job_id=db.job_id),
        response=Response(),
        current_user=user,
        db=db,  # type: ignore[arg-type]
        settings=settings,
    )
    second = await learning_roadmaps.request_learning_roadmap(
        body=learning_roadmaps.RoadmapRequest(job_id=db.job_id),
        response=Response(),
        current_user=user,
        db=db,  # type: ignore[arg-type]
        settings=settings,
    )

    assert first.operation_id == second.operation_id == queued.id
    assert first.status_url == second.status_url
    assert first.retry_after_ms == second.retry_after_ms == 1500
    rate_limit.assert_not_awaited()
