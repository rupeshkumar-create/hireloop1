"""
Tests for Aarya's auto-ingest-on-empty-search behaviour.

When job_search returns nothing, the agent can (opt-in) enqueue a durable
background job for a career-path-scoped Apify scrape.
"""

from __future__ import annotations

import uuid

import pytest

from hireloop_api.agents.aarya import tools
from hireloop_api.config import Settings
from hireloop_api.services.background_jobs import CAREER_PATH_INGEST

_USER_ID = str(uuid.uuid4())
_CAND_ID = uuid.uuid4()


class _EmptyDB:
    """Fake connection: a candidate exists but no jobs match."""

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "career_paths" in query:
            return None
        return {"id": _CAND_ID, "remote_preference": "any"}

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        return []

    async def fetchval(self, query: str, *args: object) -> object | None:
        if "background_jobs" in query and "SELECT id" in query:
            return None
        if "INSERT INTO public.background_jobs" in query:
            return uuid.uuid4()
        return None

    async def execute(self, query: str, *args: object) -> str:
        return "INSERT 0 1"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "development",
        "auto_ingest_on_empty_search": True,
        "apify_token": "test-token",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


async def _run_search(settings: Settings | None) -> dict:
    return await tools.job_search(
        _EmptyDB(),  # type: ignore[arg-type]
        _USER_ID,
        str(uuid.uuid4()),
        "growth designer",
        settings=settings,
    )


async def test_empty_search_enqueues_auto_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: dict[str, str] = {}

    async def _spy_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        payload = kwargs.get("payload") or {}
        if isinstance(payload, dict):
            fired["candidate_id"] = str(payload.get("candidate_id", ""))
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        _spy_enqueue,
    )

    out = await _run_search(_settings())
    assert out["count"] == 0
    assert out["matches"] == []
    assert fired.get("candidate_id") == str(_CAND_ID)


async def test_no_auto_ingest_when_flag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: dict[str, str] = {}

    async def _spy_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        payload = kwargs.get("payload") or {}
        if isinstance(payload, dict):
            fired["candidate_id"] = str(payload.get("candidate_id", ""))
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        _spy_enqueue,
    )

    out = await _run_search(_settings(auto_ingest_on_empty_search=False))
    assert out["count"] == 0
    assert out["matches"] == []
    assert "candidate_id" not in fired


async def test_no_auto_ingest_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: dict[str, str] = {}

    async def _spy_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        payload = kwargs.get("payload") or {}
        if isinstance(payload, dict):
            fired["candidate_id"] = str(payload.get("candidate_id", ""))
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        _spy_enqueue,
    )

    out = await _run_search(_settings(apify_token=""))
    assert out["count"] == 0
    assert out["matches"] == []
    assert "candidate_id" not in fired


async def test_no_auto_ingest_without_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    fired: dict[str, str] = {}

    async def _spy_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        payload = kwargs.get("payload") or {}
        if isinstance(payload, dict):
            fired["candidate_id"] = str(payload.get("candidate_id", ""))
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        _spy_enqueue,
    )

    out = await _run_search(None)
    assert out["count"] == 0
    assert out["matches"] == []
    assert "candidate_id" not in fired


def test_auto_ingest_flag_defaults_off() -> None:
    s = Settings(_env_file=None, environment="development")  # type: ignore[call-arg]
    assert s.auto_ingest_on_empty_search is False


async def test_empty_search_with_career_path_enqueues_path_ingest_even_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fired: dict[str, object] = {}

    class _PathDb(_EmptyDB):
        async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
            if "FROM public.career_paths" in query:
                return {
                    "id": uuid.uuid4(),
                    "current_role": "Category Planner",
                    "summary": "Move into category leadership",
                    "steps": [],
                    "target_titles": ["Category Manager", "Senior Category Manager"],
                    "target_locations": ["Bengaluru"],
                    "model": "test",
                    "prioritized_title": "Category Manager",
                    "created_at": None,
                    "updated_at": None,
                }
            return {
                "id": _CAND_ID,
                "remote_preference": "any",
                "market": "IN",
                "current_title": "Category Planner",
                "current_company": "Target",
                "full_name": "Candidate",
                "headline": "Category planner",
                "summary": "Retail category planning",
                "years_experience": 5,
                "skills": ["merchandising", "e-commerce"],
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "expected_ctc_min": None,
                "expected_ctc_max": None,
                "open_to_relocation": False,
                "location_scope": "city",
            }

    async def _spy_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        fired["kind"] = kwargs.get("kind")
        fired["payload"] = kwargs.get("payload")
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        _spy_enqueue,
    )

    session_id = str(uuid.uuid4())
    out = await tools.job_search(
        _PathDb(),  # type: ignore[arg-type]
        _USER_ID,
        session_id,
        "show me jobs",
        settings=_settings(auto_ingest_on_empty_search=False),
    )

    assert out["count"] == 0
    assert fired["kind"] == CAREER_PATH_INGEST
    assert fired["payload"] == {
        "candidate_id": str(_CAND_ID),
        "derive_from_candidate": True,
        "force_refresh": False,
        "user_id": _USER_ID,
        "session_id": session_id,
    }
