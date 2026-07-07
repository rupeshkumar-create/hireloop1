"""Canonical candidate intelligence snapshot and task-specific adapters.

This is the backend source-of-facts layer for AI and matching workflows. It does
not decide rankings or generate prompts by itself; it loads all candidate-owned
signals once, records where they came from, and exposes focused adapters for
job search, matching, resume tailoring, interview prep, and chat.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

from hireloop_api.markets import normalize_market
from hireloop_api.services.job_preferences import normalize_remote_preference
from hireloop_api.services.profile_experience import (
    build_merged_education,
    build_merged_experience,
)

_RESUME_SOURCE_NOTE = (
    "All employers, titles, dates, education, and metrics MUST match this "
    "profile exactly. Rephrase bullets for the job; never invent or alter facts."
)


class CandidateIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    user_id: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    market: str = "IN"


class CandidateProfileFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headline: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_experience: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    skills: list[str] = Field(default_factory=list)
    looking_for: str | None = None
    linkedin_url: str | None = None
    linkedin_data: dict[str, Any] = Field(default_factory=dict)
    career_profile: dict[str, Any] = Field(default_factory=dict)
    career_analysis: dict[str, Any] = Field(default_factory=dict)
    career_intelligence: dict[str, Any] = Field(default_factory=dict)
    profile_complete: bool = False
    is_active: bool = True


class CandidatePreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    expected_ctc_min: int | None = None
    expected_ctc_max: int | None = None
    current_ctc: int | None = None
    notice_period_days: int | None = None
    remote_preference: str = "any"
    open_to_relocation: bool = False
    location_scope: str = "city"
    display_currency: str = "auto"
    tailored_resume_enabled: bool = False
    share_with_recruiters: bool = True


class CandidateMemoryFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    career_facts: dict[str, Any] = Field(default_factory=dict)
    raw_state: dict[str, Any] = Field(default_factory=dict)


class CandidateGoals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    desired_title: str | None = None
    desired_industry: str | None = None
    desired_salary: int | None = None
    work_mode: str | None = None
    industry_preferences: list[str] = Field(default_factory=list)
    inferred_goals: list[str] = Field(default_factory=list)


class NegativePreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    companies: list[str] = Field(default_factory=list)
    titles: list[str] = Field(default_factory=list)


class LatestResumeFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    file_name: str | None = None
    file_path: str | None = None
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    raw_text: str | None = None
    created_at: str | None = None


class CareerPathFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    current_role: str | None = None
    summary: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    prioritized_title: str | None = None


class CandidateActivityFacts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    saved_job_ids: list[str] = Field(default_factory=list)
    applied_job_ids: list[str] = Field(default_factory=list)
    saved_jobs: list[dict[str, Any]] = Field(default_factory=list)
    applications: list[dict[str, Any]] = Field(default_factory=list)


class JobSearchHardFilters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    market: str = "IN"
    remote_preference: str = "any"
    location_scope: str = "city"
    ctc_floor: int | None = None
    excluded_companies: list[str] = Field(default_factory=list)
    excluded_titles: list[str] = Field(default_factory=list)


class JobSearchContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    market: str
    primary_titles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    desired_industry: str | None = None
    memory_summary: str = ""
    career_facts: dict[str, Any] = Field(default_factory=dict)
    hard_filters: JobSearchHardFilters
    negative_preferences: NegativePreferences = Field(default_factory=NegativePreferences)
    saved_job_ids: list[str] = Field(default_factory=list)
    applied_job_ids: list[str] = Field(default_factory=list)
    source_inventory: dict[str, bool] = Field(default_factory=dict)


class ResumeTailoringContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    headline: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_experience: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    looking_for: str | None = None
    linkedin_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    expected_ctc_min: int | None = None
    expected_ctc_max: int | None = None
    notice_period_days: int | None = None
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    career_goals: dict[str, Any] = Field(default_factory=dict)
    latest_resume_file_name: str | None = None
    source_note: str = _RESUME_SOURCE_NOTE


class CandidateIntelligenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    identity: CandidateIdentity
    profile: CandidateProfileFacts
    preferences: CandidatePreferences
    memory: CandidateMemoryFacts
    goals: CandidateGoals
    negative_preferences: NegativePreferences = Field(default_factory=NegativePreferences)
    latest_resume: LatestResumeFacts | None = None
    career_path: CareerPathFacts | None = None
    activity: CandidateActivityFacts = Field(default_factory=CandidateActivityFacts)
    provenance: dict[str, str] = Field(default_factory=dict)

    def for_job_search(self) -> JobSearchContext:
        """Broad recall context for job search and matching pipelines."""
        primary_titles = _unique_nonempty(
            [
                self.career_path.prioritized_title if self.career_path else None,
                *((self.career_path.target_titles if self.career_path else []) or []),
                self.goals.desired_title,
                self.profile.looking_for,
                self.profile.current_title,
            ]
        )
        skills = _unique_nonempty(
            [
                *self.profile.skills,
                *_list_from_parsed_resume(self.latest_resume, "skills"),
                *_linkedin_skills(self.profile.linkedin_data),
            ]
        )
        hard_filters = JobSearchHardFilters(
            market=self.identity.market,
            remote_preference=self.preferences.remote_preference,
            location_scope=self.preferences.location_scope,
            ctc_floor=self.preferences.expected_ctc_min,
            excluded_companies=self.negative_preferences.companies,
            excluded_titles=self.negative_preferences.titles,
        )
        return JobSearchContext(
            candidate_id=self.identity.candidate_id,
            market=self.identity.market,
            primary_titles=primary_titles,
            skills=skills,
            desired_industry=self.goals.desired_industry,
            memory_summary=self.memory.summary,
            career_facts=self.memory.career_facts,
            hard_filters=hard_filters,
            negative_preferences=self.negative_preferences,
            saved_job_ids=self.activity.saved_job_ids,
            applied_job_ids=self.activity.applied_job_ids,
            source_inventory={
                "profile": True,
                "resume": self.latest_resume is not None,
                "linkedin": bool(self.profile.linkedin_data),
                "memory": bool(self.memory.summary or self.memory.career_facts),
                "career_path": self.career_path is not None,
                "career_intelligence": bool(self.profile.career_intelligence),
            },
        )

    def for_resume_tailoring(self) -> ResumeTailoringContext:
        """Source-strict context for per-job tailored resume generation."""
        parsed = self.latest_resume.parsed_data if self.latest_resume else {}
        resume_experience = parsed.get("work_experience") if isinstance(parsed, dict) else None
        resume_education = parsed.get("education") if isinstance(parsed, dict) else None
        experience = build_merged_experience(
            resume_experience=[e for e in (resume_experience or []) if isinstance(e, dict)],
            linkedin_data=self.profile.linkedin_data,
            career_profile=self.profile.career_profile,
            career_intelligence=self.profile.career_intelligence,
            candidate={
                "current_title": self.profile.current_title,
                "current_company": self.profile.current_company,
                "headline": self.profile.headline,
                "summary": self.profile.summary,
            },
            skills=self.profile.skills,
        )
        education = build_merged_education(
            resume_education=[e for e in (resume_education or []) if isinstance(e, dict)],
            linkedin_data=self.profile.linkedin_data,
            career_profile=self.profile.career_profile,
        )
        return ResumeTailoringContext(
            full_name=_first_text(
                parsed.get("full_name") if isinstance(parsed, dict) else None,
                self.identity.full_name,
            ),
            email=self.identity.email,
            phone=self.identity.phone,
            headline=self.profile.headline,
            summary=_first_text(
                self.profile.summary,
                parsed.get("summary") if isinstance(parsed, dict) else None,
            ),
            current_title=self.profile.current_title,
            current_company=self.profile.current_company,
            years_experience=self.profile.years_experience,
            location_city=self.profile.location_city,
            location_state=self.profile.location_state,
            looking_for=self.profile.looking_for,
            linkedin_url=self.profile.linkedin_url,
            skills=_unique_nonempty(
                [*self.profile.skills, *_list_from_parsed_resume(self.latest_resume, "skills")]
            ),
            expected_ctc_min=self.preferences.expected_ctc_min,
            expected_ctc_max=self.preferences.expected_ctc_max,
            notice_period_days=self.preferences.notice_period_days,
            experience=experience[:12],
            education=education[:8],
            career_goals=self.goals.model_dump(exclude_none=True),
            latest_resume_file_name=self.latest_resume.file_name if self.latest_resume else None,
        )


async def load_candidate_intelligence(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID | str,
) -> CandidateIntelligenceSnapshot | None:
    """Load all candidate-owned facts required by AI and matching workflows."""
    cid = uuid.UUID(str(candidate_id))
    row = await db.fetchrow(
        """
        SELECT c.id, c.user_id, u.full_name, u.email, u.phone,
               u.market AS user_market,
               c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, c.linkedin_url, c.linkedin_data, c.career_profile,
               c.career_analysis, c.career_intelligence, c.aarya_state,
               c.expected_ctc_min, c.expected_ctc_max, c.current_ctc,
               c.notice_period_days, c.remote_preference, c.open_to_relocation,
               c.location_scope, c.market, c.display_currency,
               c.tailored_resume_enabled, c.share_with_recruiters,
               c.profile_complete, c.is_active
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        cid,
    )
    if not row:
        return None

    data = dict(row)
    aarya_state = _coerce_json(data.get("aarya_state"))
    career_facts = _coerce_json(aarya_state.get("career_facts"))
    goals = _build_goals(data, career_facts)
    latest_resume = await _load_latest_resume(db, cid)
    career_path = await _load_career_path(db, cid)
    activity = await _load_activity(db, cid)
    market = normalize_market(data.get("market") or data.get("user_market") or "IN")

    return CandidateIntelligenceSnapshot(
        identity=CandidateIdentity(
            candidate_id=str(data["id"]),
            user_id=str(data["user_id"]),
            full_name=data.get("full_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            market=market,
        ),
        profile=CandidateProfileFacts(
            headline=data.get("headline"),
            summary=data.get("summary"),
            current_title=data.get("current_title"),
            current_company=data.get("current_company"),
            years_experience=data.get("years_experience"),
            location_city=data.get("location_city"),
            location_state=data.get("location_state"),
            skills=[str(s) for s in (data.get("skills") or []) if str(s).strip()],
            looking_for=data.get("looking_for"),
            linkedin_url=data.get("linkedin_url"),
            linkedin_data=_coerce_json(data.get("linkedin_data")),
            career_profile=_coerce_json(data.get("career_profile")),
            career_analysis=_coerce_json(data.get("career_analysis")),
            career_intelligence=_coerce_json(data.get("career_intelligence")),
            profile_complete=bool(data.get("profile_complete")),
            is_active=bool(data.get("is_active", True)),
        ),
        preferences=CandidatePreferences(
            expected_ctc_min=data.get("expected_ctc_min"),
            expected_ctc_max=data.get("expected_ctc_max"),
            current_ctc=data.get("current_ctc"),
            notice_period_days=data.get("notice_period_days"),
            remote_preference=normalize_remote_preference(data.get("remote_preference")),
            open_to_relocation=bool(data.get("open_to_relocation")),
            location_scope=str(data.get("location_scope") or "city"),
            display_currency=str(data.get("display_currency") or "auto"),
            tailored_resume_enabled=bool(data.get("tailored_resume_enabled")),
            share_with_recruiters=bool(data.get("share_with_recruiters", True)),
        ),
        memory=CandidateMemoryFacts(
            summary=str(aarya_state.get("memory_summary") or ""),
            career_facts=career_facts,
            raw_state=aarya_state,
        ),
        goals=goals,
        negative_preferences=_build_negative_preferences(aarya_state),
        latest_resume=latest_resume,
        career_path=career_path,
        activity=activity,
        provenance={
            "identity": "public.users + public.candidates",
            "profile": "public.candidates",
            "preferences": "public.candidates",
            "memory_summary": "candidates.aarya_state.memory_summary",
            "career_facts": "candidates.aarya_state.career_facts",
            "resume": "public.resumes.latest_primary",
            "career_path": "public.career_paths.latest",
            "activity": "public.saved_jobs + public.job_applications",
        },
    )


async def _load_latest_resume(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> LatestResumeFacts | None:
    row = await db.fetchrow(
        """
        SELECT id, file_name, file_path, parsed_data, raw_text, created_at
        FROM public.resumes
        WHERE candidate_id = $1::uuid
        ORDER BY is_primary DESC, version DESC, created_at DESC
        LIMIT 1
        """,
        candidate_id,
    )
    if not row:
        return None
    data = dict(row)
    return LatestResumeFacts(
        id=str(data["id"]),
        file_name=data.get("file_name"),
        file_path=data.get("file_path"),
        parsed_data=_coerce_json(data.get("parsed_data")),
        raw_text=data.get("raw_text"),
        created_at=str(data["created_at"]) if data.get("created_at") is not None else None,
    )


async def _load_career_path(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> CareerPathFacts | None:
    row = await db.fetchrow(
        """
        SELECT id, current_role, summary, steps, target_titles, target_locations,
               prioritized_title
        FROM public.career_paths
        WHERE candidate_id = $1::uuid AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        candidate_id,
    )
    if not row:
        return None
    data = dict(row)
    return CareerPathFacts(
        id=str(data["id"]),
        current_role=data.get("current_role"),
        summary=data.get("summary"),
        steps=[s for s in (_coerce_json(data.get("steps")) or []) if isinstance(s, dict)],
        target_titles=_unique_nonempty(data.get("target_titles") or []),
        target_locations=_unique_nonempty(data.get("target_locations") or []),
        prioritized_title=data.get("prioritized_title"),
    )


async def _load_activity(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> CandidateActivityFacts:
    saved_rows = await db.fetch(
        """
        SELECT sj.job_id, j.title, co.name AS company_name, j.location_city,
               j.is_remote, sj.saved_at
        FROM public.saved_jobs sj
        JOIN public.jobs j ON j.id = sj.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE sj.candidate_id = $1::uuid
        ORDER BY sj.saved_at DESC
        LIMIT 50
        """,
        candidate_id,
    )
    application_rows = await db.fetch(
        """
        SELECT job_id, status, apply_type, applied_at
        FROM public.job_applications
        WHERE candidate_id = $1::uuid
        ORDER BY applied_at DESC
        LIMIT 50
        """,
        candidate_id,
    )
    saved_jobs = [_jsonable_row(r) for r in saved_rows]
    applications = [_jsonable_row(r) for r in application_rows]
    return CandidateActivityFacts(
        saved_job_ids=[str(r["job_id"]) for r in saved_rows if r.get("job_id")],
        applied_job_ids=[str(r["job_id"]) for r in application_rows if r.get("job_id")],
        saved_jobs=saved_jobs,
        applications=applications,
    )


def _build_goals(data: dict[str, Any], career_facts: dict[str, Any]) -> CandidateGoals:
    desired_title = _first_text(
        career_facts.get("desired_title"),
        data.get("looking_for"),
        _nested_get(data.get("career_intelligence"), ["goals", "explicit_goals", "desired_title"]),
    )
    desired_industry = _first_text(
        career_facts.get("desired_industry"),
        _nested_get(
            data.get("career_intelligence"), ["goals", "explicit_goals", "desired_industry"]
        ),
    )
    raw_industries = career_facts.get("industry_preference") or []
    inferred = _nested_get(data.get("career_intelligence"), ["goals", "inferred_goals"]) or []
    return CandidateGoals(
        desired_title=desired_title,
        desired_industry=desired_industry,
        desired_salary=_first_int(
            career_facts.get("desired_salary"),
            _nested_get(
                data.get("career_intelligence"), ["goals", "explicit_goals", "desired_salary"]
            ),
            data.get("expected_ctc_max"),
        ),
        work_mode=_first_text(career_facts.get("work_mode")),
        industry_preferences=_unique_nonempty(
            raw_industries if isinstance(raw_industries, list) else []
        ),
        inferred_goals=_unique_nonempty(inferred if isinstance(inferred, list) else []),
    )


def _build_negative_preferences(aarya_state: dict[str, Any]) -> NegativePreferences:
    raw = _coerce_json(aarya_state.get("negative_preferences"))
    return NegativePreferences(
        companies=_unique_nonempty(raw.get("companies") if isinstance(raw, dict) else []),
        titles=_unique_nonempty(raw.get("titles") if isinstance(raw, dict) else []),
    )


def _coerce_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(row).items()}


def _unique_nonempty(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
    return None


def _nested_get(value: Any, path: list[str]) -> Any:
    current: Any = _coerce_json(value)
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _list_from_parsed_resume(resume: LatestResumeFacts | None, key: str) -> list[str]:
    if not resume:
        return []
    raw = resume.parsed_data.get(key)
    return _unique_nonempty(raw if isinstance(raw, list) else [])


def _linkedin_skills(linkedin_data: dict[str, Any]) -> list[str]:
    apify = linkedin_data.get("apify_profile")
    if not isinstance(apify, dict):
        return []
    raw = apify.get("skills")
    return _unique_nonempty(raw if isinstance(raw, list) else [])
