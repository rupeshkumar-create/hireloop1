"""Chat-surfaced jobs must land in match_scores so history survives refresh."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from hireloop_api.agents.aarya.tools import _persist_chat_match_scores


@pytest.mark.asyncio
async def test_persist_chat_match_scores_upserts_rows() -> None:
    db = AsyncMock()
    candidate_id = uuid.uuid4()
    job_id = uuid.uuid4()

    await _persist_chat_match_scores(
        db,
        candidate_id=candidate_id,
        rows=[
            {
                "id": str(job_id),
                "overall_score": 0.81,
                "skills_score": 0.7,
                "experience_score": 0.6,
                "location_score": 0.5,
                "ctc_score": None,
                "explanation": "Shown in chat",
            }
        ],
    )

    db.executemany.assert_awaited_once()
    sql, records = db.executemany.await_args.args
    assert "INSERT INTO public.match_scores" in sql
    assert "ON CONFLICT (candidate_id, job_id)" in sql
    assert len(records) == 1
    assert records[0][1] == candidate_id
    assert records[0][2] == job_id
    assert records[0][3] == 0.81
    assert json.loads(records[0][9]) == {"source": "aarya_chat"}


@pytest.mark.asyncio
async def test_persist_chat_match_scores_skips_empty() -> None:
    db = AsyncMock()
    await _persist_chat_match_scores(db, candidate_id=uuid.uuid4(), rows=[])
    db.executemany.assert_not_awaited()
