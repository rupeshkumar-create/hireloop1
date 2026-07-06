import uuid

import pytest

from hireloop_api.config import Settings
from hireloop_api.routes.resumes import (
    _build_profile_updates_from_resume,
    _ensure_candidate_for_resume_upload,
    _prepare_candidate_resume_storage,
    apply_to_profile,
)
from hireloop_api.services.background_jobs import AARYA_AUTO_INGEST
from hireloop_api.services.resume_parser import ParsedResume


class FakeDb:
    def __init__(self) -> None:
        self.fetchrow_calls = 0
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.inserted_id = uuid.uuid4()
        self.created = False

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls += 1
        if "FROM public.users" in query:
            return {"full_name": "Rupesh Kumar"}
        if "FROM public.candidates" in query:
            if "WHERE user_id" in query:
                if not self.created:
                    return None
                return {"id": self.inserted_id}
            return {
                "id": self.inserted_id,
                "public_profile_enabled": True,
                "hide_contact_public": True,
                "public_slug": None,
            }
        return None

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        if "INSERT INTO public.candidates" in query:
            self.created = True
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
    assert db.fetchrow_calls >= 2
    insert_call = next(c for c in db.execute_calls if "INSERT INTO public.candidates" in c[0])
    assert insert_call[1][1] == "Rupesh Kumar"


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


class ApplyResumeDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        parsed = ParsedResume(
            current_title="Go-To-Market Lead",
            current_company="Candidately",
            years_experience=10,
            skills=["Artificial Intelligence", "Digital Strategy", "Automation", "Sales"],
            summary="B2B SaaS GTM for staffing agencies and recruiters.",
        )
        self._parsed_data = parsed.model_dump_json()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.resumes" in query:
            return {
                "candidate_id": self.candidate_id,
                "parsed_data": self._parsed_data,
            }
        if "FROM public.candidates" in query:
            return {
                "headline": None,
                "summary": None,
                "current_title": None,
                "current_company": None,
                "years_experience": None,
                "expected_ctc_min": None,
                "expected_ctc_max": None,
                "current_ctc": None,
                "notice_period_days": None,
                "skills": [],
                "linkedin_url": None,
                "github_url": None,
                "location_city": None,
                "location_state": None,
                "career_profile": None,
                "career_analysis": None,
            }
        return None

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "OK"


@pytest.mark.asyncio
async def test_apply_resume_enqueues_candidate_specific_job_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = ApplyResumeDb()
    enqueued: list[tuple[str, dict[str, object], str | None]] = []

    async def fake_enqueue_job(
        db_arg: object,
        *,
        kind: str,
        payload: dict[str, object],
        idempotency_key: str | None = None,
        **kwargs: object,
    ) -> uuid.UUID:
        enqueued.append((kind, payload, idempotency_key))
        return uuid.uuid4()

    monkeypatch.setattr(
        "hireloop_api.services.background_jobs.enqueue_job",
        fake_enqueue_job,
    )

    await apply_to_profile(
        resume_id=str(uuid.uuid4()),
        current_user={"id": str(uuid.uuid4())},
        settings=Settings(_env_file=None, environment="test"),  # type: ignore[call-arg]
        db=db,  # type: ignore[arg-type]
    )

    assert (
        AARYA_AUTO_INGEST,
        {"candidate_id": str(db.candidate_id)},
        f"aarya_auto_ingest:{db.candidate_id}",
    ) in enqueued
