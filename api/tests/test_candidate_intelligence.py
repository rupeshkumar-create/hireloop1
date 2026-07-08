from __future__ import annotations

import uuid
from typing import Any

import pytest

from hireloop_api.services.candidate_intelligence import load_candidate_intelligence
from hireloop_api.services.tailored_resume_profile import load_tailored_resume_profile


class FakeCandidateIntelligenceDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.saved_job_id = uuid.uuid4()
        self.applied_job_id = uuid.uuid4()

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FROM public.candidates c" in query:
            return {
                "id": self.candidate_id,
                "user_id": self.user_id,
                "full_name": "Asha Rao",
                "email": "asha@example.com",
                "phone": "+919999999999",
                "user_market": "IN",
                "headline": "Senior Growth Manager",
                "summary": "Built PLG and lifecycle growth motions.",
                "current_title": "Senior Growth Manager",
                "current_company": "Acme SaaS",
                "years_experience": 8,
                "location_city": "Bengaluru",
                "location_state": "Karnataka",
                "skills": ["PLG", "Lifecycle Marketing", "SQL"],
                "looking_for": "Head of Growth roles in SaaS",
                "linkedin_url": "https://linkedin.com/in/asha",
                "linkedin_data": {"apify_profile": {"skills": ["Retention", "Analytics"]}},
                "career_profile": {
                    "experience_career_history": {"roles": [{"company": "Acme SaaS"}]}
                },
                "career_analysis": {"recommendation": "Growth leadership"},
                "career_intelligence": {"goals": {"explicit_goals": {"desired_industry": "SaaS"}}},
                "aarya_state": {
                    "memory_summary": "Prefers remote-first SaaS growth leadership.",
                    "career_facts": {
                        "desired_title": "Head of Growth",
                        "desired_industry": "SaaS",
                        "work_mode": "Remote",
                    },
                    "negative_preferences": {
                        "companies": ["legacy corp"],
                        "titles": ["field sales"],
                    },
                },
                "expected_ctc_min": 4000000,
                "expected_ctc_max": 5500000,
                "current_ctc": 3200000,
                "notice_period_days": 30,
                "remote_preference": "remote_only",
                "open_to_relocation": True,
                "location_scope": "country",
                "market": "IN",
                "display_currency": "auto",
                "tailored_resume_enabled": True,
                "share_with_recruiters": True,
                "profile_complete": True,
                "is_active": True,
            }
        if "FROM public.resumes" in query:
            return {
                "id": uuid.uuid4(),
                "file_name": "asha-resume.pdf",
                "file_path": "resumes/asha.pdf",
                "parsed_data": {
                    "full_name": "Asha Rao",
                    "summary": "Growth leader with SaaS experience.",
                    "skills": ["Experimentation", "SQL"],
                    "work_experience": [
                        {
                            "title": "Senior Growth Manager",
                            "company": "Acme SaaS",
                            "start_date": "2021-01",
                            "end_date": None,
                        }
                    ],
                    "education": [{"degree": "MBA", "institution": "IIM"}],
                },
                "raw_text": "Asha Rao growth resume text",
                "created_at": "2026-07-01T00:00:00Z",
            }
        if "FROM public.career_paths" in query:
            return {
                "id": uuid.uuid4(),
                "current_role": "Growth Manager",
                "summary": "Move toward growth leadership.",
                "steps": [{"title": "Head of Growth"}],
                "target_titles": ["Head of Growth", "Growth Lead", "Lifecycle Marketing Lead"],
                "target_locations": ["Bengaluru", "Remote"],
                "prioritized_title": "Head of Growth",
            }
        return None

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        if "FROM public.saved_jobs" in query:
            return [
                {
                    "job_id": self.saved_job_id,
                    "title": "Head of Growth",
                    "company_name": "Modern SaaS",
                    "location_city": "Bengaluru",
                    "is_remote": True,
                    "saved_at": "2026-07-02T00:00:00Z",
                }
            ]
        if "FROM public.job_applications" in query:
            return [
                {
                    "job_id": self.applied_job_id,
                    "status": "applied",
                    "apply_type": "direct",
                    "applied_at": "2026-07-03T00:00:00Z",
                }
            ]
        return []


@pytest.mark.asyncio
async def test_candidate_intelligence_snapshot_merges_all_candidate_sources() -> None:
    db = FakeCandidateIntelligenceDb()

    snapshot = await load_candidate_intelligence(db, db.candidate_id)

    assert snapshot is not None
    assert snapshot.identity.full_name == "Asha Rao"
    assert snapshot.profile.current_title == "Senior Growth Manager"
    assert snapshot.preferences.remote_preference == "remote_only"
    assert snapshot.goals.desired_title == "Head of Growth"
    assert snapshot.memory.summary == "Prefers remote-first SaaS growth leadership."
    assert snapshot.latest_resume is not None
    assert snapshot.latest_resume.parsed_data["skills"] == ["Experimentation", "SQL"]
    assert snapshot.career_path is not None
    assert snapshot.career_path.prioritized_title == "Head of Growth"
    assert snapshot.activity.saved_job_ids == [str(db.saved_job_id)]
    assert snapshot.activity.applied_job_ids == [str(db.applied_job_id)]
    assert snapshot.provenance["memory_summary"] == "candidates.aarya_state.memory_summary"


@pytest.mark.asyncio
async def test_job_search_adapter_is_broad_and_resume_adapter_is_source_strict() -> None:
    db = FakeCandidateIntelligenceDb()
    snapshot = await load_candidate_intelligence(db, db.candidate_id)
    assert snapshot is not None

    job_ctx = snapshot.for_job_search()
    resume_ctx = snapshot.for_resume_tailoring()

    assert job_ctx.primary_titles[:2] == ["Head of Growth", "Growth Lead"]
    assert "Senior Growth Manager" in job_ctx.primary_titles
    assert "SQL" in job_ctx.skills
    assert job_ctx.hard_filters.remote_preference == "remote_only"
    assert job_ctx.negative_preferences.companies == ["legacy corp"]
    assert str(db.saved_job_id) in job_ctx.saved_job_ids

    assert resume_ctx.source_note.startswith("All employers, titles, dates")
    assert resume_ctx.full_name == "Asha Rao"
    assert resume_ctx.experience[0]["company"] == "Acme SaaS"
    assert resume_ctx.career_goals["desired_title"] == "Head of Growth"
    assert resume_ctx.latest_resume_file_name == "asha-resume.pdf"


@pytest.mark.asyncio
async def test_tailored_resume_profile_uses_candidate_intelligence_adapter() -> None:
    db = FakeCandidateIntelligenceDb()

    profile = await load_tailored_resume_profile(db, db.candidate_id)  # type: ignore[arg-type]

    assert profile is not None
    assert profile["career_goals"]["desired_title"] == "Head of Growth"
    assert profile["latest_resume_file_name"] == "asha-resume.pdf"
    assert profile["source_note"].startswith("All employers, titles, dates")


@pytest.mark.asyncio
async def test_null_negative_preferences_do_not_crash_profile_load() -> None:
    """Regression: kit prepare crashed with 'NoneType is not iterable' when
    aarya_state.negative_preferences.companies/titles were JSON null."""
    from hireloop_api.services.candidate_intelligence import _build_negative_preferences

    prefs = _build_negative_preferences(
        {"negative_preferences": {"companies": None, "titles": None}}
    )
    assert prefs.companies == []
    assert prefs.titles == []

    db = FakeCandidateIntelligenceDb()
    # Inject a null companies list into the fake candidate row.
    original_fetchrow = db.fetchrow

    async def fetchrow_with_null_prefs(query: str, *args):  # type: ignore[no-untyped-def]
        row = await original_fetchrow(query, *args)
        if isinstance(row, dict) and "aarya_state" in row:
            row = dict(row)
            row["aarya_state"] = {
                **(row["aarya_state"] or {}),
                "negative_preferences": {"companies": None, "titles": None},
            }
        return row

    db.fetchrow = fetchrow_with_null_prefs  # type: ignore[method-assign]
    snapshot = await load_candidate_intelligence(db, db.candidate_id)
    assert snapshot is not None
    assert snapshot.negative_preferences.companies == []
    # Kit profile load must also succeed.
    profile = await load_tailored_resume_profile(db, db.candidate_id)  # type: ignore[arg-type]
    assert profile is not None
