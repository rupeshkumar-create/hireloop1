"""Tests for lexical instant job shelf."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hireloop_api.services.instant_shelf import fetch_instant_shelf


@pytest.mark.asyncio
async def test_instant_shelf_uses_job_search_then_starter_fallback() -> None:
    db = AsyncMock()
    candidate_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    db.fetchrow = AsyncMock(
        return_value={
            "id": candidate_id,
            "looking_for": "Product Manager",
            "current_title": None,
            "market": "IN",
            "remote_preference": "any",
        }
    )
    settings = MagicMock()

    job_cards = [{"job_id": str(uuid.uuid4()), "title": "PM"}]
    starter = [{"job_id": str(uuid.uuid4()), "title": "APM"}]

    with (
        patch(
            "hireloop_api.agents.aarya.tools.job_search",
            new_callable=AsyncMock,
            return_value={"job_cards": job_cards},
        ) as mock_search,
        patch(
            "hireloop_api.routes.matches._fetch_starter_market_jobs",
            new_callable=AsyncMock,
            return_value=starter,
        ) as mock_starter,
    ):
        out = await fetch_instant_shelf(db, user_id=user_id, settings=settings, limit=10)

    mock_search.assert_awaited_once()
    session_id = mock_search.await_args.args[2]
    assert str(uuid.UUID(session_id)) == session_id
    mock_starter.assert_awaited_once()
    assert len(out) == 2
    assert out[0]["title"] == "PM"
    assert out[1]["title"] == "APM"
    db.executemany.assert_awaited_once()
    score_rows = db.executemany.await_args.args[1]
    assert {str(row[2]) for row in score_rows} == {
        job_cards[0]["job_id"],
        starter[0]["job_id"],
    }
    impression_calls = [
        call for call in db.execute.await_args_list if "candidate_job_impressions" in call.args[0]
    ]
    assert len(impression_calls) == 1


@pytest.mark.asyncio
async def test_instant_shelf_skips_starter_when_enough_cards() -> None:
    db = AsyncMock()
    candidate_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    db.fetchrow = AsyncMock(
        return_value={
            "id": candidate_id,
            "looking_for": "Engineer",
            "current_title": None,
            "market": "IN",
            "remote_preference": "remote",
        }
    )
    settings = MagicMock()
    job_cards = [{"job_id": str(uuid.uuid4()), "title": f"Role {i}"} for i in range(6)]

    with (
        patch(
            "hireloop_api.agents.aarya.tools.job_search",
            new_callable=AsyncMock,
            return_value={"job_cards": job_cards},
        ),
        patch(
            "hireloop_api.routes.matches._fetch_starter_market_jobs",
            new_callable=AsyncMock,
        ) as mock_starter,
    ):
        out = await fetch_instant_shelf(db, user_id=user_id, settings=settings, limit=10)

    mock_starter.assert_not_awaited()
    assert len(out) == 6
    db.executemany.assert_awaited_once()
