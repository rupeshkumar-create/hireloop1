"""Legacy voice completion remains compatible without mutating profile data."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from hireloop_api.routes import voice
from hireloop_api.routes.voice import VoiceSessionCreate, create_voice_session
from hireloop_api.routes.voice_sessions import CareerCallResponse


class LegacyDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        normalized = " ".join(query.split())
        if "FROM public.candidates" in normalized:
            return {"id": self.candidate_id}
        raise AssertionError(f"Unrecognised fetchrow query: {normalized}")

    async def execute(self, query: str, *args: object) -> str:
        normalized = " ".join(query.split())
        self.execute_calls.append((normalized, args))
        if "INSERT INTO public.voice_sessions" in normalized:
            return "INSERT 0 1"
        raise AssertionError(f"Unrecognised execute query: {normalized}")


@pytest.mark.asyncio
async def test_legacy_completion_without_session_id_never_updates_candidate_profile() -> None:
    db = LegacyDb()
    result = await create_voice_session(
        VoiceSessionCreate(
            duration_seconds=120,
            status="completed",
            conversation_id=str(uuid.uuid4()),
        ),
        current_user={"id": str(uuid.uuid4())},
        db=db,
    )

    assert result["status"] == "completed"
    assert any("INSERT INTO public.voice_sessions" in sql for sql, _ in db.execute_calls)
    assert all("UPDATE public.candidates" not in sql for sql, _ in db.execute_calls)


@pytest.mark.asyncio
async def test_legacy_existing_session_delegates_without_inserting_or_mutating_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = LegacyDb()
    session_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    calls: list[dict[str, object]] = []

    async def complete_existing(**kwargs: object) -> CareerCallResponse:
        calls.append(kwargs)
        return CareerCallResponse(
            id=str(session_id),
            conversation_id=str(conversation_id),
            status="completed",
        )

    monkeypatch.setattr(voice, "_complete_owned_career_call", complete_existing)
    result = await create_voice_session(
        VoiceSessionCreate(
            session_id=session_id,
            duration_seconds=120,
            status="completed",
            conversation_id=str(conversation_id),
        ),
        current_user={"id": str(uuid.uuid4())},
        db=db,
    )

    assert result["id"] == str(session_id)
    assert len(calls) == 1
    assert calls[0]["session_id"] == session_id
    assert db.execute_calls == []


@pytest.mark.asyncio
async def test_legacy_existing_session_rejects_cancelled_without_second_row() -> None:
    db = LegacyDb()
    with pytest.raises(HTTPException) as exc:
        await create_voice_session(
            VoiceSessionCreate(
                session_id=uuid.uuid4(),
                duration_seconds=0,
                status="cancelled",
            ),
            current_user={"id": str(uuid.uuid4())},
            db=db,
        )

    assert exc.value.status_code == 400
    assert db.execute_calls == []
