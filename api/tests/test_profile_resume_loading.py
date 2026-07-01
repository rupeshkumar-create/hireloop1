from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from hireloop_api.config import Settings
from hireloop_api.routes.me import get_my_profile


class FakeProfileDb:
    def __init__(self) -> None:
        self.user_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM public.users" in query:
            return {
                "id": self.user_id,
                "email": "rupesh@example.com",
                "phone": None,
                "full_name": "Rupesh Kumar",
                "role": "candidate",
                "phone_verified": False,
                "avatar_url": None,
            }
        if "FROM public.candidates" in query:
            return {
                "id": self.candidate_id,
                "headline": "Software Engineer",
                "summary": None,
                "current_title": "Software Engineer",
                "current_company": "Infosys",
                "years_experience": 5,
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "skills": ["Python"],
                "profile_complete": True,
                "visibility": "open_to_matches",
                "looking_for": None,
                "is_active": True,
                "linkedin_data": {},
            }
        if "FROM public.resumes" in query:
            assert "deleted_at" not in query
            return {
                "parsed_data": {
                    "work_experience": [{"company": "Infosys", "title": "Software Engineer"}],
                    "education": [],
                }
            }
        return None


@pytest.mark.asyncio
async def test_profile_loads_latest_resume_without_deleted_at_filter() -> None:
    db = FakeProfileDb()
    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]

    with patch(
        "hireloop_api.services.background_jobs.enqueue_job",
        new=AsyncMock(return_value=uuid.uuid4()),
    ):
        profile = await get_my_profile(
            current_user={"id": str(db.user_id), "full_name": "Rupesh Kumar"},
            settings=settings,
            db=db,  # type: ignore[arg-type]
        )

    assert profile["experience"][0]["company"] == "Infosys"
    assert profile["experience"][0]["title"] == "Software Engineer"
    assert profile["experience"][0]["source"] == "resume"
