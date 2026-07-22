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


@pytest.mark.parametrize(
    ("invalid_state", "invalid_value"),
    [
        ({"schema_version": 2}, 2),
        ({"turn_count": -1}, -1),
        ({"turn_count": "1"}, "1"),
        ({"unexpected_field": True}, True),
    ],
)
def test_coverage_rejects_invalid_persisted_contract(
    invalid_state: dict[str, object],
    invalid_value: object,
) -> None:
    with pytest.raises(ValidationError) as error:
        CareerInterviewCoverage.model_validate(invalid_state)

    assert str(invalid_value) in str(error.value)


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


@pytest.mark.parametrize("answer", ["I don't want to", "I do not want to"])
def test_minimal_refusal_is_declined(answer: str) -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.COMPENSATION)

    updated = record_candidate_answer(state, answer)

    assert updated.declined_topics == [InterviewTopic.COMPENSATION]
    assert updated.covered_topics == []


@pytest.mark.parametrize(
    "answer",
    ["I don't want to go into that", "I do not want to go into that"],
)
def test_general_want_to_refusal_is_declined(answer: str) -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.COMPENSATION)

    updated = record_candidate_answer(state, answer)

    assert updated.declined_topics == [InterviewTopic.COMPENSATION]
    assert updated.covered_topics == []


@pytest.mark.parametrize(
    ("topic", "answer"),
    [
        (
            InterviewTopic.TARGET_ROLES,
            "I don't want to manage people; I prefer an IC role",
        ),
        (
            InterviewTopic.RELOCATION,
            "I don't want to relocate, but remote work is fine",
        ),
    ],
)
def test_want_to_preference_is_covered_not_declined(
    topic: InterviewTopic,
    answer: str,
) -> None:
    state = CareerInterviewCoverage(current_focus=topic)

    updated = record_candidate_answer(state, answer)

    assert updated.covered_topics == [topic]
    assert updated.declined_topics == []


@pytest.mark.parametrize(
    ("topic", "answer"),
    [
        (
            InterviewTopic.RELOCATION,
            "I prefer not to relocate; remote work is fine",
        ),
        (
            InterviewTopic.TARGET_ROLES,
            "I'd rather not manage people; an IC role suits me",
        ),
        (
            InterviewTopic.COMPENSATION,
            "I prefer not to share my current CTC, but my target is 25 LPA",
        ),
        (
            InterviewTopic.WORK_MODE,
            "I'd rather not work night shifts; day shifts are fine",
        ),
    ],
)
def test_prefer_not_with_meaningful_detail_is_covered_not_declined(
    topic: InterviewTopic,
    answer: str,
) -> None:
    state = CareerInterviewCoverage(current_focus=topic)

    updated = record_candidate_answer(state, answer)

    assert updated.covered_topics == [topic]
    assert updated.declined_topics == []


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


def test_long_standalone_uncertainty_is_not_covered() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.SKILLS)

    updated = record_candidate_answer(
        state,
        "Honestly I am not sure what my strongest skills are",
    )

    assert updated.covered_topics == []
    assert updated.declined_topics == []


def test_comma_only_uncertainty_is_not_covered() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.SKILLS)

    updated = record_candidate_answer(state, "I don't know, maybe")

    assert updated.covered_topics == []
    assert updated.declined_topics == []


@pytest.mark.parametrize(
    "answer",
    [
        "I don't know my official title; I lead platform engineering",
        "I don't know the exact stack. I mainly use Python and Go",
    ],
)
def test_uncertainty_with_substantive_hard_boundary_continuation_is_covered(
    answer: str,
) -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.SKILLS)

    updated = record_candidate_answer(state, answer)

    assert updated.covered_topics == [InterviewTopic.SKILLS]
    assert updated.declined_topics == []


@pytest.mark.parametrize(
    ("topic", "answer"),
    [
        (
            InterviewTopic.NOTICE_PERIOD,
            "I'm not sure of the exact date, but my notice period is 30 days.",
        ),
        (
            InterviewTopic.COMPENSATION,
            "I don't know the exact number, but my target is 25 LPA.",
        ),
        (
            InterviewTopic.COMPENSATION,
            "I don't want to skip this; my expected CTC is 25 LPA.",
        ),
    ],
)
def test_substantive_mixed_answer_is_covered_and_not_reasked(
    topic: InterviewTopic,
    answer: str,
) -> None:
    earlier_topics = [
        candidate_topic
        for candidate_topic in (
            InterviewTopic.CURRENT_WORK,
            InterviewTopic.IMPACT,
            InterviewTopic.SKILLS,
            InterviewTopic.TARGET_ROLES,
            InterviewTopic.LOCATION_SCOPE,
            InterviewTopic.WORK_MODE,
            InterviewTopic.NOTICE_PERIOD,
        )
        if candidate_topic is not topic
    ]
    state = CareerInterviewCoverage(
        covered_topics=earlier_topics,
        current_focus=topic,
    )

    updated = record_candidate_answer(state, answer)
    next_focus = select_next_focus(updated, elapsed_seconds=200)

    assert topic in updated.covered_topics
    assert topic not in updated.declined_topics
    assert next_focus.topic is not topic


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
