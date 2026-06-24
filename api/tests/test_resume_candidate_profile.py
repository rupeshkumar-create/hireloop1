import uuid

import pytest

from hireloop_api.routes.resumes import (
    _build_profile_updates_from_resume,
    _ensure_candidate_for_resume_upload,
    _prepare_candidate_resume_storage,
)
from hireloop_api.services.resume_parser import ParsedResume


class FakeDb:
    def __init__(self) -> None:
        self.fetchrow_calls = 0
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.inserted_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls += 1
        if self.fetchrow_calls == 1:
            return None
        return {"id": self.inserted_id}

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return "INSERT 0 1"


@pytest.mark.asyncio
async def test_resume_upload_creates_missing_candidate_profile() -> None:
    db = FakeDb()
    user_id = uuid.uuid4()

    candidate = await _ensure_candidate_for_resume_upload(
        db,
        user_id=str(user_id),
        headline="Rupesh Kumar",
    )

    assert candidate["id"] == db.inserted_id
    assert db.fetchrow_calls == 2
    assert "INSERT INTO public.candidates" in db.execute_calls[0][0]
    assert db.execute_calls[0][1] == (user_id, "Rupesh Kumar")


@pytest.mark.asyncio
async def test_resume_upload_marks_new_resume_as_primary_and_updates_path() -> None:
    db = FakeDb()
    candidate_id = uuid.uuid4()
    storage_path = "user-id/resume-id.pdf"

    await _prepare_candidate_resume_storage(
        db,  # type: ignore[arg-type]
        candidate_id=str(candidate_id),
        storage_path=storage_path,
    )

    demote_query, demote_args = db.execute_calls[0]
    update_query, update_args = db.execute_calls[1]

    assert "UPDATE public.resumes" in demote_query
    assert "is_primary = FALSE" in demote_query
    assert demote_args == (candidate_id,)
    assert "UPDATE public.candidates" in update_query
    assert "resume_path = $2" in update_query
    assert "COALESCE" not in update_query
    assert update_args == (candidate_id, storage_path)


def test_resume_profile_updates_include_structured_career_json() -> None:
    candidate = {
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
    parsed = ParsedResume(
        current_title="Senior Software Engineer",
        current_company="Infosys",
        years_experience=7,
        skills=["Python", "React"],
        career_profile={"profile_demographics": {"full_name": "Rupesh Kumar"}},
        career_analysis={"current_position": "Senior Software Engineer"},
    )

    updates, fields_updated = _build_profile_updates_from_resume(candidate, parsed)

    assert updates["career_profile"] == {"profile_demographics": {"full_name": "Rupesh Kumar"}}
    assert updates["career_analysis"] == {"current_position": "Senior Software Engineer"}
    assert "career_profile" in fields_updated
    assert "career_analysis" in fields_updated
