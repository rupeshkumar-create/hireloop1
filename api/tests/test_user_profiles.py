"""Tests for dual-role / registered-candidate profile flags."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from hireloop_api.services.user_profiles import user_has_registered_candidate_profile


class ProfileFlagDb:
    def __init__(
        self,
        *,
        user_role: str = "recruiter",
        candidate_id: uuid.UUID | None = None,
        onboarding_complete: bool = False,
        profile_complete: bool = False,
        linkedin_url: str | None = None,
        has_resume: bool = False,
        has_voice: bool = False,
    ) -> None:
        self.user_role = user_role
        self.candidate_id = candidate_id or uuid.uuid4()
        self.onboarding_complete = onboarding_complete
        self.profile_complete = profile_complete
        self.linkedin_url = linkedin_url
        self.has_resume = has_resume
        self.has_voice = has_voice

    async def fetchrow(self, query: str, user_id: uuid.UUID) -> dict[str, Any] | None:
        if "FROM public.users u" in query:
            if self.candidate_id is None:
                return {
                    "candidate_id": None,
                    "onboarding_complete": False,
                    "profile_complete": False,
                    "linkedin_url": None,
                    "user_role": self.user_role,
                }
            return {
                "candidate_id": self.candidate_id,
                "onboarding_complete": self.onboarding_complete,
                "profile_complete": self.profile_complete,
                "linkedin_url": self.linkedin_url,
                "user_role": self.user_role,
            }
        return None

    async def fetchval(self, query: str, candidate_id: uuid.UUID) -> bool:
        if "public.resumes" in query:
            return self.has_resume
        if "voice_sessions" in query:
            return self.has_voice
        return False


@pytest.mark.asyncio
async def test_recruiter_stub_is_not_registered_candidate() -> None:
    db = ProfileFlagDb(user_role="recruiter")
    assert await user_has_registered_candidate_profile(db, uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_recruiter_with_completed_candidate_onboarding_can_switch() -> None:
    db = ProfileFlagDb(user_role="recruiter", onboarding_complete=True)
    assert await user_has_registered_candidate_profile(db, uuid.uuid4()) is True


@pytest.mark.asyncio
async def test_candidate_bootstrap_row_counts_as_registered() -> None:
    db = ProfileFlagDb(user_role="candidate")
    assert await user_has_registered_candidate_profile(db, uuid.uuid4()) is True


@pytest.mark.asyncio
async def test_no_candidate_row_is_not_registered() -> None:
    db = ProfileFlagDb(user_role="recruiter")
    db.candidate_id = None
    assert await user_has_registered_candidate_profile(db, uuid.uuid4()) is False
