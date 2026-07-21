"""Tests for Aarya's deterministic career interview coverage policy."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from hireloop_api.models.career_interview import (
    ActiveCareerInterview,
    CareerInterviewCoverage,
    InterviewTopic,
    NextInterviewFocus,
)
from hireloop_api.services.career_interview import (
    record_candidate_answer,
    select_next_focus,
)


def test_models_expose_the_versioned_interview_contract() -> None:
    coverage = CareerInterviewCoverage()
    interview = ActiveCareerInterview(
        session_id=uuid4(),
        candidate_id=uuid4(),
        conversation_id=uuid4(),
        started_at=datetime.now(UTC),
        coverage=coverage,
    )

    assert coverage.schema_version == 1
    assert coverage.covered_topics == []
    assert coverage.declined_topics == []
    assert coverage.question_history == []
    assert coverage.current_focus is None
    assert coverage.turn_count == 0
    assert coverage.completion_reason is None
    assert interview.coverage == coverage
    assert {topic.value for topic in InterviewTopic} == {
        "current_work",
        "impact",
        "skills",
        "languages",
        "target_roles",
        "industries",
        "location_scope",
        "work_mode",
        "compensation",
        "notice_period",
        "relocation",
        "deal_breakers",
    }


def test_question_history_is_typed_as_interview_topics() -> None:
    coverage = CareerInterviewCoverage(question_history=[InterviewTopic.SKILLS])

    assert coverage.question_history == [InterviewTopic.SKILLS]
    assert coverage.question_history[0] is InterviewTopic.SKILLS
    with pytest.raises(ValidationError):
        CareerInterviewCoverage(question_history=["unknown_topic"])


def test_next_interview_focus_requires_an_explicit_topic() -> None:
    with pytest.raises(ValidationError):
        NextInterviewFocus(prompt_hint="Continue the interview.")


def test_first_focus_is_current_work_before_time_limit() -> None:
    result = select_next_focus(CareerInterviewCoverage(), elapsed_seconds=60)

    assert result.topic is InterviewTopic.CURRENT_WORK
    assert result.should_wrap is False
    assert result.prompt_hint


def test_answering_current_work_marks_only_it_and_increments_turn_count() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.CURRENT_WORK)

    result = record_candidate_answer(
        state,
        "I lead platform engineering for a fintech company.",
    )

    assert result.covered_topics == [InterviewTopic.CURRENT_WORK]
    assert result.declined_topics == []
    assert result.turn_count == 1


def test_declined_compensation_is_not_selected_again() -> None:
    state = CareerInterviewCoverage(
        covered_topics=[
            InterviewTopic.CURRENT_WORK,
            InterviewTopic.IMPACT,
            InterviewTopic.SKILLS,
            InterviewTopic.TARGET_ROLES,
            InterviewTopic.LOCATION_SCOPE,
            InterviewTopic.WORK_MODE,
            InterviewTopic.NOTICE_PERIOD,
        ],
        current_focus=InterviewTopic.COMPENSATION,
    )

    updated = record_candidate_answer(state, "I'd rather not discuss that.")
    next_focus = select_next_focus(updated, elapsed_seconds=120)

    assert updated.declined_topics == [InterviewTopic.COMPENSATION]
    assert InterviewTopic.COMPENSATION not in updated.covered_topics
    assert next_focus.topic is InterviewTopic.RELOCATION


def test_wraps_at_exactly_fourteen_minutes() -> None:
    result = select_next_focus(CareerInterviewCoverage(), elapsed_seconds=14 * 60)

    assert result.topic is None
    assert result.should_wrap is True
    assert "recap" in result.prompt_hint.lower()
    assert "uncert" in result.prompt_hint.lower()
    assert "close" in result.prompt_hint.lower()


def test_non_answer_is_not_covered_and_is_asked_again() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.CURRENT_WORK)

    updated = record_candidate_answer(state, "I don't know yet")
    next_focus = select_next_focus(updated, elapsed_seconds=100)

    assert updated.covered_topics == []
    assert updated.declined_topics == []
    assert updated.turn_count == 1
    assert next_focus.topic is InterviewTopic.CURRENT_WORK


def test_record_candidate_answer_does_not_mutate_input() -> None:
    state = CareerInterviewCoverage(
        covered_topics=[InterviewTopic.CURRENT_WORK],
        question_history=[InterviewTopic.IMPACT],
        current_focus=InterviewTopic.IMPACT,
        turn_count=2,
    )
    snapshot = state.model_copy(deep=True)

    updated = record_candidate_answer(state, "I reduced deployment time by half.")

    assert state == snapshot
    assert updated is not state
    assert updated.covered_topics is not state.covered_topics
    assert updated.question_history is not state.question_history


def test_completed_and_declined_topics_are_skipped_in_priority_order() -> None:
    state = CareerInterviewCoverage(
        covered_topics=[InterviewTopic.CURRENT_WORK, InterviewTopic.SKILLS],
        declined_topics=[InterviewTopic.IMPACT, InterviewTopic.TARGET_ROLES],
    )

    result = select_next_focus(state, elapsed_seconds=200)

    assert result.topic is InterviewTopic.LOCATION_SCOPE


def test_all_topics_exhausted_wraps() -> None:
    topics = list(InterviewTopic)
    state = CareerInterviewCoverage(
        covered_topics=topics[:6],
        declined_topics=topics[6:],
    )

    result = select_next_focus(state, elapsed_seconds=300)

    assert result.topic is None
    assert result.should_wrap is True
    assert "recap" in result.prompt_hint.lower()
    assert "close" in result.prompt_hint.lower()


def test_short_answer_does_not_count_as_covered() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.SKILLS)

    updated = record_candidate_answer(state, "Python mostly")

    assert updated.covered_topics == []
    assert updated.turn_count == 1


def test_prompt_hints_respect_sensitive_topic_framing() -> None:
    compensation = select_next_focus(
        CareerInterviewCoverage(
            covered_topics=[
                InterviewTopic.CURRENT_WORK,
                InterviewTopic.IMPACT,
                InterviewTopic.SKILLS,
                InterviewTopic.TARGET_ROLES,
                InterviewTopic.LOCATION_SCOPE,
                InterviewTopic.WORK_MODE,
                InterviewTopic.NOTICE_PERIOD,
            ],
        ),
        elapsed_seconds=100,
    )
    languages = select_next_focus(
        CareerInterviewCoverage(
            covered_topics=[
                InterviewTopic.CURRENT_WORK,
                InterviewTopic.IMPACT,
                InterviewTopic.SKILLS,
                InterviewTopic.TARGET_ROLES,
                InterviewTopic.LOCATION_SCOPE,
                InterviewTopic.WORK_MODE,
                InterviewTopic.NOTICE_PERIOD,
                InterviewTopic.COMPENSATION,
                InterviewTopic.RELOCATION,
                InterviewTopic.INDUSTRIES,
            ],
        ),
        elapsed_seconds=100,
    )

    assert compensation.topic is InterviewTopic.COMPENSATION
    assert "optional" in compensation.prompt_hint.lower()
    assert languages.topic is InterviewTopic.LANGUAGES
    assert "proficien" in languages.prompt_hint.lower()
    assert "you" in languages.prompt_hint.lower()
