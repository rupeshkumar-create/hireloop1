"""Retention service tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hireloop_api.services.retention import (
    count_new_matches_since,
    fetch_return_summary,
    send_daily_match_digest,
)


@pytest.mark.asyncio
async def test_count_new_matches_since_first_visit() -> None:
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"n": 12})
    n = await count_new_matches_since(
        db,
        candidate_id=uuid.uuid4(),
        since=None,
        market="IN",
    )
    assert n == 12


@pytest.mark.asyncio
async def test_count_new_matches_since_with_timestamp() -> None:
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"n": 3})
    since = datetime.now(UTC) - timedelta(days=1)
    n = await count_new_matches_since(
        db,
        candidate_id=uuid.uuid4(),
        since=since,
        market="IN",
    )
    assert n == 3


@pytest.mark.asyncio
async def test_fetch_return_summary_with_new_matches() -> None:
    db = AsyncMock()
    cid = uuid.uuid4()
    uid = uuid.uuid4()
    since = datetime.now(UTC) - timedelta(days=1)
    db.fetchrow = AsyncMock(
        return_value={
            "id": cid,
            "looking_for": "Product Manager",
            "current_title": None,
            "market": "IN",
            "last_visit_at": since,
        }
    )
    settings = MagicMock(public_app_url="https://www.hireschema.com", allowed_origins=[])

    with patch(
        "hireloop_api.services.retention.count_new_matches_since",
        new_callable=AsyncMock,
        return_value=4,
    ):
        out = await fetch_return_summary(db, user_id=uid, settings=settings)

    assert out["ok"] is True
    assert out["new_matches_count"] == 4
    assert out["proactive_message"] is not None
    assert "4 new role" in out["proactive_message"]


@pytest.mark.asyncio
async def test_daily_digest_skips_when_deduped() -> None:
    db = AsyncMock()
    settings = MagicMock()
    with patch(
        "hireloop_api.services.notifications._already_notified",
        new_callable=AsyncMock,
        return_value=True,
    ):
        out = await send_daily_match_digest(db, settings, user_id=str(uuid.uuid4()))
    assert out["sent"] is False
    assert out["skipped"] == "deduped"
