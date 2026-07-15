"""Atomic intro claim before Gmail send — prevents duplicate cold emails."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from hireloop_api.agents.nitya import tools as nitya_tools


class _FakeDb:
    def __init__(self, status: str = "draft_ready") -> None:
        self.status = status
        self.updates: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        self.updates.append((query, args))
        if "status = 'sending'" in query and "RETURNING" in query:
            if self.status in ("draft_ready", "drafting", "failed"):
                self.status = "sending"
                return {
                    "id": args[0],
                    "status": "sending",
                    "draft_email": {"subject": "Hi"},
                    "direction": "candidate_to_hm",
                }
            return None
        if "status = 'sent'" in query and "RETURNING" in query:
            if self.status == "sending":
                self.status = "sent"
                return {"id": args[0]}
            return None
        return None

    async def execute(self, query: str, *args: Any) -> str:
        self.updates.append((query, args))
        if "status = 'failed'" in query and self.status == "sending":
            self.status = "failed"
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_claim_intro_for_send_wins_once() -> None:
    db = _FakeDb("draft_ready")
    cid = str(uuid.uuid4())
    iid = str(uuid.uuid4())

    first = await nitya_tools.claim_intro_for_send(db, intro_id=iid, candidate_id=cid)  # type: ignore[arg-type]
    assert first is not None
    assert db.status == "sending"

    second = await nitya_tools.claim_intro_for_send(db, intro_id=iid, candidate_id=cid)  # type: ignore[arg-type]
    assert second is None


@pytest.mark.asyncio
async def test_claim_intro_allows_failed_retry() -> None:
    db = _FakeDb("failed")
    claimed = await nitya_tools.claim_intro_for_send(
        db,  # type: ignore[arg-type]
        intro_id=str(uuid.uuid4()),
        candidate_id=str(uuid.uuid4()),
    )
    assert claimed is not None
    assert db.status == "sending"


@pytest.mark.asyncio
async def test_release_intro_send_failure_marks_failed() -> None:
    db = _FakeDb("sending")
    await nitya_tools.release_intro_send_failure(
        db,  # type: ignore[arg-type]
        intro_id=str(uuid.uuid4()),
        error_message="gmail down",
    )
    assert db.status == "failed"
