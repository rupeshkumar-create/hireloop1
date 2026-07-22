"""Typed state contracts for Aarya's career interview."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    covered_topics: list[InterviewTopic] = Field(default_factory=list)
    declined_topics: list[InterviewTopic] = Field(default_factory=list)
    question_history: list[InterviewTopic] = Field(default_factory=list)
    current_focus: InterviewTopic | None = None
    turn_count: int = Field(default=0, ge=0, strict=True)
    completion_reason: str | None = None


class NextInterviewFocus(BaseModel):
    """Policy decision for Aarya's next interview turn."""

    model_config = ConfigDict(extra="forbid")

    topic: InterviewTopic | None
    prompt_hint: str
    should_wrap: bool = False


class ActiveCareerInterview(BaseModel):
    """Identity and coverage state for an active interview session."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    candidate_id: UUID
    conversation_id: UUID
    started_at: datetime
    coverage: CareerInterviewCoverage
