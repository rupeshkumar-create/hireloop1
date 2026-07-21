"""Typed state contracts for Aarya's career interview."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class InterviewTopic(StrEnum):
    """Candidate-controlled topics covered during a career interview."""

    CURRENT_WORK = "current_work"
    IMPACT = "impact"
    SKILLS = "skills"
    LANGUAGES = "languages"
    TARGET_ROLES = "target_roles"
    INDUSTRIES = "industries"
    LOCATION_SCOPE = "location_scope"
    WORK_MODE = "work_mode"
    COMPENSATION = "compensation"
    NOTICE_PERIOD = "notice_period"
    RELOCATION = "relocation"
    DEAL_BREAKERS = "deal_breakers"


class CareerInterviewCoverage(BaseModel):
    """Versioned interview progress stored for a single session."""

    schema_version: int = 1
    covered_topics: list[InterviewTopic] = Field(default_factory=list)
    declined_topics: list[InterviewTopic] = Field(default_factory=list)
    question_history: list[str] = Field(default_factory=list)
    current_focus: InterviewTopic | None = None
    turn_count: int = 0
    completion_reason: str | None = None


class NextInterviewFocus(BaseModel):
    """Policy decision for Aarya's next interview turn."""

    topic: InterviewTopic | None = None
    prompt_hint: str
    should_wrap: bool = False


class ActiveCareerInterview(BaseModel):
    """Identity and coverage state for an active interview session."""

    session_id: UUID
    candidate_id: UUID
    conversation_id: UUID
    started_at: datetime
    coverage: CareerInterviewCoverage
