"""Candidate-aware query planning for Apify job ingestion.

The ingester should not ask a job board a single prompt-shaped query. This
module turns the canonical candidate intelligence snapshot into concrete,
source-attributed title, skill, and location inputs for board recall.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hireloop_api.services.candidate_intelligence import CandidateIntelligenceSnapshot


class CandidateJobIngestDiagnostics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_inventory: dict[str, bool] = Field(default_factory=dict)
    title_sources: dict[str, list[str]] = Field(default_factory=dict)
    skill_sources: dict[str, list[str]] = Field(default_factory=dict)
    location_sources: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class CandidateJobIngestPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    market: str
    remote_preference: str
    title_inputs: list[str] = Field(default_factory=list)
    current_title: str | None = None
    skills: list[str] = Field(default_factory=list)
    raw_locations: list[str] = Field(default_factory=list)
    diagnostics: CandidateJobIngestDiagnostics = Field(
        default_factory=CandidateJobIngestDiagnostics
    )


_TITLE_FIELD_NAMES = (
    "desired_title",
    "target_title",
    "preferred_title",
    "next_role",
    "next_title",
)
_TITLE_LIST_FIELD_NAMES = ("target_titles", "target_roles", "preferred_titles", "roles")


def build_candidate_job_ingest_plan(
    snapshot: CandidateIntelligenceSnapshot,
    *,
    max_title_inputs: int = 12,
    max_skills: int = 18,
) -> CandidateJobIngestPlan:
    """Build broad-but-attributed board-search inputs for one candidate."""

    title_sources: dict[str, list[str]] = {}
    skill_sources: dict[str, list[str]] = {}
    location_sources: dict[str, list[str]] = {}

    title_inputs: list[str] = []
    skills: list[str] = []
    raw_locations: list[str] = []

    def add_titles(source: str, values: list[Any]) -> None:
        added: list[str] = []
        for value in values:
            text = _clean_title_like_text(value)
            if _append_unique(title_inputs, text):
                added.append(text)
        if added:
            title_sources[source] = added

    def add_skills(source: str, values: list[Any]) -> None:
        added: list[str] = []
        for value in values:
            text = _text(value)
            if _append_unique(skills, text):
                added.append(text)
        if added:
            skill_sources[source] = added

    def add_locations(source: str, values: list[Any]) -> None:
        added: list[str] = []
        for value in values:
            text = _text(value)
            if _append_unique(raw_locations, text):
                added.append(text)
        if added:
            location_sources[source] = added

    if snapshot.preferences.remote_preference == "remote_only":
        add_locations("remote_preference", ["Remote"])

    career_path = snapshot.career_path
    if career_path:
        add_titles(
            "career_path",
            [career_path.prioritized_title, *career_path.target_titles],
        )
        add_locations("career_path", career_path.target_locations)

    add_titles("goals", [snapshot.goals.desired_title])
    add_titles("memory", _titles_from_memory(snapshot.memory.career_facts))
    add_titles(
        "career_intelligence",
        _titles_from_career_intelligence(snapshot.profile.career_intelligence),
    )
    add_titles("profile", [snapshot.profile.looking_for])
    add_titles(
        "resume",
        _titles_from_resume(snapshot.latest_resume.parsed_data if snapshot.latest_resume else {}),
    )
    add_titles("current_profile", [snapshot.profile.current_title])

    add_skills("profile", snapshot.profile.skills)
    add_skills(
        "resume",
        _skills_from_resume(snapshot.latest_resume.parsed_data if snapshot.latest_resume else {}),
    )
    add_skills("goals", [snapshot.goals.desired_industry, *snapshot.goals.industry_preferences])
    add_skills("memory", [snapshot.memory.career_facts.get("desired_industry")])

    add_locations("profile", [snapshot.profile.location_city, snapshot.profile.location_state])

    notes: list[str] = []
    if not career_path:
        notes.append("career_path_missing")
    if not title_inputs:
        notes.append("no_title_inputs")
    if not raw_locations:
        notes.append("no_candidate_locations")

    return CandidateJobIngestPlan(
        candidate_id=snapshot.identity.candidate_id,
        market=snapshot.identity.market,
        remote_preference=snapshot.preferences.remote_preference,
        title_inputs=title_inputs[:max_title_inputs],
        current_title=snapshot.profile.current_title,
        skills=skills[:max_skills],
        raw_locations=raw_locations,
        diagnostics=CandidateJobIngestDiagnostics(
            source_inventory=snapshot.for_job_search().source_inventory,
            title_sources=title_sources,
            skill_sources=skill_sources,
            location_sources=location_sources,
            notes=notes,
        ),
    )


def _titles_from_memory(career_facts: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for field in _TITLE_FIELD_NAMES:
        values.append(career_facts.get(field))
    for field in _TITLE_LIST_FIELD_NAMES:
        raw = career_facts.get(field)
        if isinstance(raw, list):
            values.extend(raw)
    return values


def _titles_from_career_intelligence(data: dict[str, Any]) -> list[Any]:
    goals = data.get("goals") if isinstance(data, dict) else None
    explicit = goals.get("explicit_goals") if isinstance(goals, dict) else None
    if not isinstance(explicit, dict):
        return []
    return [explicit.get("desired_title"), explicit.get("target_title")]


def _titles_from_resume(parsed_data: dict[str, Any]) -> list[Any]:
    values: list[Any] = [
        parsed_data.get("current_title"),
        parsed_data.get("headline"),
        parsed_data.get("title"),
    ]
    work = parsed_data.get("work_experience")
    if isinstance(work, list):
        for entry in work[:3]:
            if isinstance(entry, dict):
                values.append(entry.get("title"))
    return values


def _skills_from_resume(parsed_data: dict[str, Any]) -> list[Any]:
    raw = parsed_data.get("skills")
    if not isinstance(raw, list):
        return []
    values: list[Any] = []
    for item in raw:
        if isinstance(item, dict):
            values.append(item.get("name") or item.get("skill"))
        else:
            values.append(item)
    return values


def _clean_title_like_text(value: Any) -> str:
    text = _text(value)
    low = text.lower()
    for suffix in (" roles in ", " jobs in ", " positions in "):
        if suffix in low:
            return text[: low.index(suffix)].strip()
    for suffix in (" roles", " jobs", " positions"):
        if low.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _append_unique(target: list[str], value: str) -> bool:
    if not value:
        return False
    key = value.lower()
    if any(existing.lower() == key for existing in target):
        return False
    target.append(value)
    return True
