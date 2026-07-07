from __future__ import annotations

from hireloop_api.services.apify.candidate_job_query_plan import build_candidate_job_ingest_plan
from hireloop_api.services.candidate_intelligence import (
    CandidateActivityFacts,
    CandidateGoals,
    CandidateIdentity,
    CandidateIntelligenceSnapshot,
    CandidateMemoryFacts,
    CandidatePreferences,
    CandidateProfileFacts,
    CareerPathFacts,
    LatestResumeFacts,
)


def _snapshot() -> CandidateIntelligenceSnapshot:
    return CandidateIntelligenceSnapshot(
        identity=CandidateIdentity(candidate_id="cand-1", user_id="user-1", market="IN"),
        profile=CandidateProfileFacts(
            current_title="Senior Growth Manager",
            location_city="Bengaluru",
            location_state="Karnataka",
            skills=["PLG", "Lifecycle Marketing"],
            looking_for="Head of Growth roles in SaaS",
            career_intelligence={
                "goals": {
                    "explicit_goals": {
                        "desired_title": "VP Growth",
                        "desired_industry": "B2B SaaS",
                    }
                }
            },
        ),
        preferences=CandidatePreferences(remote_preference="remote_only", location_scope="country"),
        memory=CandidateMemoryFacts(
            summary="Prefers remote-first SaaS growth leadership.",
            career_facts={
                "desired_title": "Head of Growth",
                "target_roles": ["Growth Product Manager", "Lifecycle Lead"],
                "desired_industry": "B2B SaaS",
                "work_mode": "Remote",
            },
        ),
        goals=CandidateGoals(desired_title="Head of Growth", desired_industry="B2B SaaS"),
        latest_resume=LatestResumeFacts(
            id="resume-1",
            parsed_data={
                "current_title": "Growth Lead",
                "skills": ["Experimentation", "SQL"],
                "work_experience": [{"title": "Lifecycle Marketing Manager"}],
            },
        ),
        career_path=CareerPathFacts(
            id="path-1",
            target_titles=["Head of Growth", "Growth Lead"],
            target_locations=["Bengaluru", "Remote"],
            prioritized_title="Head of Growth",
        ),
        activity=CandidateActivityFacts(),
    )


def test_candidate_job_ingest_plan_uses_path_memory_goals_and_resume() -> None:
    plan = build_candidate_job_ingest_plan(_snapshot(), max_title_inputs=8, max_skills=8)

    assert plan.title_inputs[:2] == ["Head of Growth", "Growth Lead"]
    assert "VP Growth" in plan.title_inputs
    assert "Growth Product Manager" in plan.title_inputs
    assert "Head of Growth roles in SaaS" not in plan.title_inputs
    assert "Experimentation" in plan.skills
    assert "Lifecycle Marketing" in plan.skills
    assert plan.raw_locations[:2] == ["Remote", "Bengaluru"]
    assert plan.market == "IN"
    assert plan.remote_preference == "remote_only"
    assert plan.diagnostics.title_sources["career_path"] == ["Head of Growth", "Growth Lead"]
    assert "memory" in plan.diagnostics.title_sources
    assert plan.diagnostics.source_inventory["resume"] is True


def test_candidate_job_ingest_plan_falls_back_without_career_path() -> None:
    snapshot = _snapshot()
    snapshot.career_path = None
    snapshot.goals.desired_title = None
    snapshot.memory.career_facts = {}

    plan = build_candidate_job_ingest_plan(snapshot, max_title_inputs=6)

    assert plan.title_inputs[0] == "VP Growth"
    assert "Growth Lead" in plan.title_inputs
    assert "Senior Growth Manager" in plan.title_inputs
    assert plan.raw_locations == ["Remote", "Bengaluru", "Karnataka"]
