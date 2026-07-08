from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hireloop_api.routes.me import _ensure_candidate_row


def _candidate_row(user_id: uuid.UUID, candidate_id: uuid.UUID) -> dict[str, Any]:
    return {
        "id": candidate_id,
        "user_id": user_id,
        "market": "IN",
        "headline": "New candidate",
        "summary": None,
        "current_title": None,
        "current_company": None,
        "years_experience": None,
        "location_city": None,
        "location_state": None,
        "skills": [],
        "profile_complete": False,
        "onboarding_complete": False,
        "visibility": "open_to_matches",
        "looking_for": None,
        "remote_preference": "any",
        "open_to_relocation": False,
        "location_scope": "country",
        "expected_ctc_min": None,
        "expected_ctc_max": None,
        "current_ctc": None,
        "notice_period_days": 30,
        "display_currency": "auto",
        "public_slug": None,
        "public_profile_enabled": True,
        "hide_contact_public": True,
        "share_with_recruiters": True,
        "tailored_resume_enabled": False,
        "is_active": True,
        "linkedin_url": None,
        "linkedin_data": {},
        "career_profile": {},
        "career_analysis": {},
    }


class CandidateBootstrapDb:
    def __init__(self, *, existing: bool) -> None:
        self.user_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()
        self.existing = existing
        self.inserted = False
        self.insert_query = ""

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FROM public.candidates" in query and "WHERE user_id = $1::uuid" in query:
            if self.existing or self.inserted:
                return _candidate_row(self.user_id, self.candidate_id)
            return None

        if query.lstrip().startswith("INSERT INTO public.candidates"):
            self.inserted = True
            self.insert_query = query
            return _candidate_row(self.user_id, self.candidate_id)

        if "SELECT full_name FROM public.users" in query:
            return {"full_name": "Rupesh Kumar"}

        if "FROM public.candidates" in query and "WHERE id = $1::uuid" in query:
            return _candidate_row(self.user_id, self.candidate_id)

        return None


@pytest.mark.asyncio
async def test_ensure_candidate_row_reuses_existing_live_candidate() -> None:
    db = CandidateBootstrapDb(existing=True)

    row = await _ensure_candidate_row(db, db.user_id)  # type: ignore[arg-type]

    assert row["id"] == db.candidate_id
    assert db.inserted is False


@pytest.mark.asyncio
async def test_ensure_candidate_row_uses_idempotent_upsert_for_missing_candidate() -> None:
    db = CandidateBootstrapDb(existing=False)

    with patch(
        "hireloop_api.services.public_profile.bootstrap_candidate_public_profile",
        new=AsyncMock(),
    ):
        row = await _ensure_candidate_row(db, db.user_id)  # type: ignore[arg-type]

    assert row["id"] == db.candidate_id
    assert "ON CONFLICT (user_id) DO UPDATE" in db.insert_query
