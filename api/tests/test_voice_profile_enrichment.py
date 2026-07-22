"""Legacy voice completion remains compatible without mutating profile data."""

from __future__ import annotations

import uuid

import pytest

from hireloop_api.routes.voice import VoiceSessionCreate, create_voice_session


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
