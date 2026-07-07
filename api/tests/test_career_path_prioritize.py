"""Tests for career path prioritization."""

from __future__ import annotations

import uuid

import pytest

from hireloop_api.routes.career import PrioritizePathRequest, prioritize_career_path
from hireloop_api.services.background_jobs import CAREER_PATH_INGEST
from hireloop_api.services.career_path import _serialize_path


def test_serialize_path_includes_prioritized_title() -> None:
    row = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "current_role": "Engineer",
        "summary": "Growing into leadership",
        "steps": [],
        "target_titles": ["Senior Engineer"],
        "target_locations": ["Bengaluru"],
        "model": "test",
        "prioritized_title": "Staff Engineer",
        "created_at": None,
        "updated_at": None,
    }
    out = _serialize_path(row)
    assert out["prioritized_title"] == "Staff Engineer"


async def test_prioritize_path_enqueues_immediate_job_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_id = uuid.uuid4()
    fired: dict[str, object] = {}

    class _Db:
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "SELECT id FROM public.candidates" in query:
                return {"id": candidate_id}
            if "location_city" in query:
                return {
                    "location_city": "Bengaluru",
                    "location_state": "Karnataka",
                }
            return None

    async def _fake_prioritize(
        db: object,
        candidate_id_arg: str,
        title: str,
        selected_titles: list[str] | None = None,
    ) -> dict:
        assert candidate_id_arg == str(candidate_id)
        return {
            "id": str(uuid.uuid4()),
            "current_role": "Category Planner",
            "summary": "Move into category leadership",
            "steps": [],
            "target_titles": selected_titles or [title],
            "target_locations": ["Bengaluru"],
            "model": "test",
            "prioritized_title": title,
            "created_at": None,
            "updated_at": None,
        }

    async def _spy_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        fired["kind"] = kwargs.get("kind")
        fired["payload"] = kwargs.get("payload")
        fired["idempotency_key"] = kwargs.get("idempotency_key")
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.career_path.CareerPathService.prioritize",
        _fake_prioritize,
    )
    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        _spy_enqueue,
    )

    result = await prioritize_career_path(
        PrioritizePathRequest(
            title="Category Manager",
            selected_titles=["Category Manager", "Senior Category Manager"],
        ),
        current_user={"id": str(uuid.uuid4())},
        db=_Db(),  # type: ignore[arg-type]
    )

    assert result["path"]["prioritized_title"] == "Category Manager"
    assert fired["kind"] == CAREER_PATH_INGEST
    assert fired["payload"] == {
        "candidate_id": str(candidate_id),
        "derive_from_candidate": True,
    }
    assert fired["idempotency_key"] == f"career_path_ingest:{candidate_id}"
