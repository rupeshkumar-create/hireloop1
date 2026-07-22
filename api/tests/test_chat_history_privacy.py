"""Ordinary Aarya history must never surface private career-call transcripts."""

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
