"""Ordinary Aarya history must never surface private career-call transcripts."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from hireloop_api.routes import chat

USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.asyncio
async def test_primary_history_filters_private_rows_and_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    candidate_id = uuid4()
    conversation_id = uuid4()
    db.fetchrow.return_value = {"id": candidate_id}
    db.fetch.return_value = []
    db.fetchval.return_value = 0
    monkeypatch.setattr(
        chat,
        "get_or_create_primary_conversation",
        AsyncMock(return_value=str(conversation_id)),
    )

    result = await chat.get_user_chat_history(
        current_user={"id": str(USER_ID)},
        db=db,
        limit=25,
        offset=5,
    )

    row_sql = db.fetch.await_args.args[0]
    total_sql = db.fetchval.await_args.args[0]
    assert "m.voice_session_id IS NULL" in row_sql
    assert "m.voice_session_id IS NULL" in total_sql
    assert result["messages"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_conversation_messages_filter_private_rows() -> None:
    db = AsyncMock()
    db.fetch.return_value = []

    result = await chat.get_messages(
        conversation_id=str(uuid4()),
        current_user={"id": str(USER_ID)},
        db=db,
        limit=20,
        offset=3,
    )

    row_sql = db.fetch.await_args.args[0]
    assert "m.voice_session_id IS NULL" in row_sql
    assert result == []


@pytest.mark.asyncio
async def test_session_message_counts_filter_private_rows() -> None:
    db = AsyncMock()
    db.fetch.return_value = []

    result = await chat.list_sessions(
        current_user={"id": str(USER_ID)},
        db=db,
    )

    sql = db.fetch.await_args.args[0]
    assert "m.voice_session_id IS NULL" in sql
    assert result == []


@pytest.mark.asyncio
async def test_action_preview_uses_latest_ordinary_turn_when_private_turn_is_newer() -> None:
    ordinary_user_at = datetime(2026, 7, 22, 8, tzinfo=UTC)
    action_at = ordinary_user_at + timedelta(seconds=10)
    private_user_at = action_at + timedelta(seconds=10)
    job = {"id": "job-1", "title": "Backend Engineer"}
    kit = {"job_id": "job-1", "status": "ready"}

    class _ActionDb:
        last_user_sql = ""

        async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
            return [
                {"action_type": "job_search", "created_at": action_at, "result": {"jobs": [job]}},
                {
                    "action_type": "prepare_application_kit",
                    "created_at": action_at,
                    "result": {"kits": [kit]},
                },
            ]

        async def fetchval(self, query: str, *args: object) -> datetime:
            self.last_user_sql = query
            # Model the real mixed transcript: without the privacy predicate the
            # newer private answer wins and hides ordinary-turn action previews.
            if "voice_session_id IS NULL" not in query:
                return private_user_at
            return ordinary_user_at

    db = _ActionDb()

    result = await chat.get_actions(
        conversation_id=str(uuid4()),
        current_user={"id": str(USER_ID)},
        db=db,  # type: ignore[arg-type]
    )

    assert "voice_session_id IS NULL" in db.last_user_sql
    assert result["turn_count"] == 2
    assert result["jobs"] == [job]
    assert result["application_kits"] == [kit]
