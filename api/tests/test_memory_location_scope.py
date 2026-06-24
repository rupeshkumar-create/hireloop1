"""
Memory extractor persists location_scope stated in chat (HIR-44 follow-up to the
location-scope feature) and keeps open_to_relocation in sync — verified with a
capturing fake connection (no DB / LLM).
"""

from __future__ import annotations

import uuid

from hireloop_api.services.memory import CandidateMemoryService

_CID = str(uuid.uuid4())


class _CaptureConn:
    def __init__(self) -> None:
        self.query: str | None = None
        self.args: tuple = ()

    async def execute(self, query: str, *args: object) -> str:
        self.query = query
        self.args = args
        return "UPDATE 1"


async def test_location_scope_persists_and_syncs_relocation() -> None:
    db = _CaptureConn()
    profile = {"location_scope": "city", "skills": []}
    change_log = await CandidateMemoryService._apply_profile_updates(
        db,  # type: ignore[arg-type]
        _CID,
        profile,
        {"location_scope": "country"},
    )
    assert any(c["field"] == "location_scope" and c["new"] == "country" for c in change_log)
    assert "location_scope =" in (db.query or "")
    assert "open_to_relocation =" in (db.query or "")
    assert "country" in db.args and True in db.args  # scope value + derived relocation


async def test_invalid_location_scope_ignored() -> None:
    db = _CaptureConn()
    change_log = await CandidateMemoryService._apply_profile_updates(
        db,  # type: ignore[arg-type]
        _CID,
        {"location_scope": "city", "skills": []},
        {"location_scope": "galaxy"},
    )
    assert change_log == []
    assert db.query is None  # nothing written


async def test_unchanged_scope_is_noop() -> None:
    db = _CaptureConn()
    change_log = await CandidateMemoryService._apply_profile_updates(
        db,  # type: ignore[arg-type]
        _CID,
        {"location_scope": "country", "skills": []},
        {"location_scope": "country"},
    )
    assert change_log == []
