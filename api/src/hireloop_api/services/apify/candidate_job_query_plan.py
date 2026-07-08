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


class CandidateJobTitleVariant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str
    source_title: str
    rank: int = 0
    reason: str = "exact"


class CandidateJobIngestPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    market: str
    remote_preference: str
    title_inputs: list[str] = Field(default_factory=list)
    title_variants: list[CandidateJobTitleVariant] = Field(default_factory=list)
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
        title_variants=build_title_query_variants(
            title_inputs[:max_title_inputs],
            max_variants_per_title=5,
        ),
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


def build_title_query_variants(
    titles: list[str],
    *,
    max_variants_per_title: int = 5,
    max_total: int = 24,
) -> list[CandidateJobTitleVariant]:
    """Expand preferred titles into board-search variants while preserving rank."""
    variants: list[CandidateJobTitleVariant] = []
    seen: set[str] = set()
    source_titles = _unique_nonempty(titles)

    per_title_counts: dict[str, int] = {}

    def add_variant(source_title: str, query: str, reason: str) -> None:
        if len(variants) >= max_total:
            return
        if per_title_counts.get(source_title, 0) >= max_variants_per_title:
            return
        cleaned = _clean_title_like_text(query)
        key = cleaned.lower()
        if not cleaned or key in seen:
            return
        # Single-token skills ("python", "figma") are not Google Jobs queries.
        if " " not in cleaned and key not in {
            "founder",
            "recruiter",
            "designer",
            "analyst",
            "engineer",
        }:
            return
        seen.add(key)
        rank = per_title_counts.get(source_title, 0)
        variants.append(
            CandidateJobTitleVariant(
                query=cleaned,
                source_title=source_title,
                rank=rank,
                reason=reason,
            )
        )
        per_title_counts[source_title] = rank + 1

    for source_title in source_titles:
        add_variant(source_title, source_title, "exact")

    for source_title in source_titles:
        for query in _role_title_synonyms(source_title):
            add_variant(source_title, query, "synonym")
            if len(variants) >= max_total:
                break
        if len(variants) >= max_total:
            break

    return variants


def _role_title_synonyms(title: str) -> list[str]:
    low = _text(title).lower()
    variants: list[str] = []

    def add(*values: str) -> None:
        variants.extend(values)

    designish = any(token in low for token in ("design", "designer", "ux", "ui"))
    productish = "product" in low
    headish = any(token in low for token in ("head", "director", "chief", "vp"))
    leadish = "lead" in low or "manager" in low
    if designish and productish and headish:
        add(
            "Head of Design",
            "Design Head",
            "Design Lead",
            "Lead Product Designer",
            "Product Design Manager",
            "Product Design Lead",
            "UX Design Lead",
        )
    elif designish and headish:
        add(
            "Head of Design",
            "Design Head",
            "Design Director",
            "Design Lead",
            "Lead Designer",
            "Product Design Manager",
        )
    elif designish and leadish:
        add(
            "Design Lead",
            "Lead Product Designer",
            "Product Design Manager",
            "Product Designer",
            "UX Designer",
        )
    elif designish:
        add("Product Designer", "UX Designer", "UI/UX Designer", "Visual Designer")

    if "product manager" in low or (productish and "manager" in low):
        add("Product Manager", "Senior Product Manager", "Product Lead", "Group Product Manager")
    if "growth" in low:
        add("Head of Growth", "Growth Lead", "Growth Manager", "Lifecycle Marketing Lead")
    if "gtm" in low or "go to market" in low or "go-to-market" in low:
        add("Head of GTM", "GTM Lead", "Go-to-Market Manager", "Revenue Operations Manager")
    if "customer success" in low:
        add("Customer Success Manager", "Client Success Manager", "Customer Success Lead")

    return _unique_nonempty(variants)


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
    if not text:
        return ""
    low = text.lower()
    # Headlines / soft-skill blobs are not Google Jobs queries.
    if len(text) > 80 or text.count("|") >= 2:
        return ""
    junk_markers = (
        "helping ",
        "passionate",
        "results-driven",
        "detail-oriented",
        "looking for",
        "open to",
        "seeking ",
    )
    if any(marker in low for marker in junk_markers) and not any(
        role in low
        for role in (
            "manager",
            "engineer",
            "designer",
            "analyst",
            "lead",
            "director",
            "head",
            "specialist",
        )
    ):
        return ""
    for suffix in (" roles in ", " jobs in ", " positions in "):
        if suffix in low:
            return text[: low.index(suffix)].strip()
    for suffix in (" roles", " jobs", " positions"):
        if low.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _unique_nonempty(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _append_unique(target: list[str], value: str) -> bool:
    if not value:
        return False
    key = value.lower()
    if any(existing.lower() == key for existing in target):
        return False
    target.append(value)
    return True
