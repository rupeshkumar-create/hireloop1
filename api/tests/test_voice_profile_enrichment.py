import uuid

import pytest

from hireloop_api.routes.voice import _apply_parsed_profile_fields
from hireloop_api.services.resume_parser import ParsedResume


class FakeDb:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        return {
            "headline": None,
            "summary": None,
            "current_title": None,
            "current_company": None,
            "years_experience": None,
            "skills": [],
            "linkedin_url": None,
            "github_url": None,
            "location_city": None,
            "location_state": None,
        }

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    async def fetchval(self, query: str, *args: object) -> object:
        # enqueue_job: idempotency SELECT -> no existing job; INSERT RETURNING id -> a uuid.
        return uuid.uuid4() if "INSERT" in query else None


@pytest.mark.asyncio
async def test_apply_parsed_voice_fields_updates_profile() -> None:
    db = FakeDb()
    user_id = uuid.uuid4()
    candidate_id = uuid.uuid4()

    await _apply_parsed_profile_fields(
        db=db,
        user_id=str(user_id),
        candidate_id=str(candidate_id),
        parsed=ParsedResume(
            current_title="Software Engineer",
            current_company="Infosys",
            years_experience=5,
            skills=["python", "react"],
        ),
        consent_purpose="voice_profile_enrichment",
    )

    update_query, update_args = db.execute_calls[0]
    assert "UPDATE public.candidates" in update_query
    assert update_args[0] == candidate_id
    assert "current_title" in update_query
    assert "profile_complete" in update_query
    assert any("consent_log" in query for query, _ in db.execute_calls)
