from __future__ import annotations

import json

import pytest

from hireloop_api.agents.aarya import tools


class _ProgressDb:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def execute(self, query: str, *args: object) -> str:
        assert "INSERT INTO public.agent_actions" in query
        self.rows.append(
            {
                "agent": args[0],
                "user_id": args[1],
                "session_id": args[2],
                "action_type": args[3],
                "payload": json.loads(str(args[4])),
                "result": json.loads(str(args[5])),
            }
        )
        return "INSERT 0 1"


@pytest.mark.asyncio
async def test_write_auto_ingest_progress_uses_agent_actions() -> None:
    db = _ProgressDb()

    await tools._write_auto_ingest_progress(
        db,  # type: ignore[arg-type]
        user_id="11111111-1111-1111-1111-111111111111",
        session_id="22222222-2222-2222-2222-222222222222",
        phase="searching",
        result={"query": "Head of Design", "step": 2, "total": 5},
    )

    assert db.rows == [
        {
            "agent": "aarya",
            "user_id": "11111111-1111-1111-1111-111111111111",
            "session_id": "22222222-2222-2222-2222-222222222222",
            "action_type": "job_ingest_progress",
            "payload": {"phase": "searching"},
            "result": {"query": "Head of Design", "step": 2, "total": 5},
        }
    ]
