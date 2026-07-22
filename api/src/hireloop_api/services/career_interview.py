"""Pure coverage policy for Aarya's career interview."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, ConfigDict

from hireloop_api.models.career_interview import (
    ActiveCareerInterview,
    CareerInterviewCoverage,
    InterviewTopic,
    NextInterviewFocus,
)

INTERVIEW_TOPIC_PRIORITY: tuple[InterviewTopic, ...] = (
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
    InterviewTopic.LANGUAGES,
    InterviewTopic.DEAL_BREAKERS,
)

PROMPT_HINTS: dict[InterviewTopic, str] = {
    InterviewTopic.CURRENT_WORK: "Ask what the candidate does in their current or most recent work.",
    InterviewTopic.IMPACT: "Ask for a concrete outcome or impact they are proud of.",
    InterviewTopic.SKILLS: "Ask which skills they use most and want to keep building.",
    InterviewTopic.TARGET_ROLES: "Ask which roles and responsibilities they want next.",
    InterviewTopic.LOCATION_SCOPE: "Ask which Indian cities or location scope they would consider.",
    InterviewTopic.WORK_MODE: "Ask whether they prefer remote, hybrid, or on-site work.",
    InterviewTopic.NOTICE_PERIOD: "Ask about their notice period or earliest possible start date.",
    InterviewTopic.COMPENSATION: (
        "Make compensation optional, then ask their preferred INR/LPA range if they wish to share."
    ),
    InterviewTopic.RELOCATION: "Ask whether relocation within India is possible or off the table.",
    InterviewTopic.INDUSTRIES: "Ask which industries interest them and which they want to avoid.",
    InterviewTopic.LANGUAGES: (
        "Ask which languages you use and invite the candidate to declare their own proficiency."
    ),
    InterviewTopic.DEAL_BREAKERS: "Ask about any role, employer, or working-condition deal-breakers.",
}

_WRAP_HINT = "Recap what was learned, name any uncertainty, and close the interview warmly."
_PREFER_NOT_REFUSAL_PATTERN = re.compile(r"\b(?:rather|prefer) not\b")
_SKIP_REFUSAL_PATTERN = re.compile(r"\bskip this\b")
_WANT_TO_REFUSAL_PATTERN = re.compile(
    r"^\s*(?:i\s+)?(?:don't|do not) want to"
    r"(?:\s+(?:discuss|share|answer|talk(?: about)?|go into|say|tell)\b"
    r"(?:\s+[^,;.!?]+)?)?[.!?]*\s*$"
)
_NEGATED_SKIP_PATTERN = re.compile(r"\b(?:(?:don't|do not) want to|not) skip this\b")
_NON_ANSWER_PATTERN = re.compile(r"\b(?:don't know|do not know|not sure|no idea)\b")
_CONTINUATION_PATTERN = re.compile(
    r"(?:\b(?:but|however|although|though|yet)\b|[;.!?])(?P<detail>.*)$"
)
_SUBSTANTIVE_FACT_PATTERN = re.compile(r"\b\d|\b(?:lpa|ctc|days?)\b")
_CONTRAST_FILLER_WORDS = frozenset(
    {
        "am",
        "do",
        "don't",
        "honestly",
        "i",
        "idea",
        "just",
        "know",
        "maybe",
        "no",
        "not",
        "perhaps",
        "really",
        "still",
        "sure",
        "yet",
    }
)


class CareerInterviewTurn(BaseModel):
    """Typed result passed from persistence into Aarya's request state."""

    model_config = ConfigDict(extra="forbid")

    coverage: CareerInterviewCoverage
    focus: InterviewTopic | None
    prompt_hint: str
    should_wrap: bool
    state_version: int


class ActiveCareerInterviewNotFoundError(LookupError):
    """Raised when a requested call is not active and owned by the candidate."""


class CareerInterviewExpiredError(RuntimeError):
    """Raised after an expired call is durably completed at its time limit."""


def _coverage_from_jsonb(value: object) -> CareerInterviewCoverage:
    if isinstance(value, str):
        return CareerInterviewCoverage.model_validate_json(value)
    if isinstance(value, Mapping):
        return CareerInterviewCoverage.model_validate(dict(value))
    raise ValueError("Career interview state must be a JSON object")


def _active_interview_from_row(row: Mapping[str, Any]) -> ActiveCareerInterview:
    return ActiveCareerInterview(
        session_id=row["session_id"],
        candidate_id=row["candidate_id"],
        conversation_id=row["conversation_id"],
        started_at=row["started_at"],
        coverage=_coverage_from_jsonb(row["state"]),
    )


async def load_active_interview(
    db: asyncpg.Connection,
    session_id: UUID,
    candidate_id: UUID,
) -> ActiveCareerInterview | None:
    """Load a candidate-owned active career interview at a typed boundary."""
    row = await db.fetchrow(
        """
        SELECT vs.id AS session_id,
               vs.candidate_id,
               vs.conversation_id,
               vs.started_at,
               cis.state,
               cis.state_version
        FROM public.voice_sessions vs
        JOIN public.career_interview_states cis
          ON cis.session_id = vs.id AND cis.candidate_id = vs.candidate_id
        WHERE vs.id = $1::uuid
          AND vs.candidate_id = $2::uuid
          AND vs.session_type = 'career_chat'
          AND vs.status = 'active'
          AND vs.conversation_id IS NOT NULL
          AND vs.started_at IS NOT NULL
        """,
        session_id,
        candidate_id,
    )
    return _active_interview_from_row(row) if row is not None else None


async def record_turn_and_select_focus(
    db: asyncpg.Connection,
    *,
    session_id: UUID,
    candidate_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    content: str,
    content_type: str,
) -> CareerInterviewTurn:
    """Atomically persist one private answer and advance its locked call state."""
    async with db.transaction():
        row = await db.fetchrow(
            """
            SELECT vs.id AS session_id,
                   vs.candidate_id,
                   vs.conversation_id,
                   vs.started_at,
                   cis.state,
                   cis.state_version
            FROM public.voice_sessions vs
            JOIN public.career_interview_states cis
              ON cis.session_id = vs.id AND cis.candidate_id = vs.candidate_id
            WHERE vs.id = $1::uuid
              AND vs.candidate_id = $2::uuid
              AND vs.session_type = 'career_chat'
              AND vs.status = 'active'
              AND vs.conversation_id IS NOT NULL
              AND vs.started_at IS NOT NULL
            FOR UPDATE OF vs, cis
            """,
            session_id,
            candidate_id,
        )
        if row is None or row["conversation_id"] != conversation_id:
            raise ActiveCareerInterviewNotFoundError

        interview = _active_interview_from_row(row)
        now = await db.fetchval("SELECT clock_timestamp()")
        if not isinstance(now, datetime):
            raise ValueError("Database clock must be a timestamp")
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        started_at = interview.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        elapsed_seconds = max(0.0, (now - started_at).total_seconds())
        expired = elapsed_seconds >= 15 * 60
        if expired:
            await db.execute(
                """
                UPDATE public.voice_sessions
                SET status = 'completed',
                    ended_at = started_at + INTERVAL '15 minutes',
                    duration_secs = 900,
                    completion_reason = 'time_limit',
                    updated_at = $3::timestamptz
                WHERE id = $1::uuid
                  AND candidate_id = $2::uuid
                  AND status = 'active'
                """,
                session_id,
                candidate_id,
                now,
            )
        else:
            updated = record_candidate_answer(interview.coverage, content)
            next_focus = select_next_focus(updated, elapsed_seconds=elapsed_seconds)
            updated.current_focus = next_focus.topic
            if next_focus.topic is not None:
                updated.question_history.append(next_focus.topic)

            state_version = int(row["state_version"]) + 1
            await db.execute(
                """
                UPDATE public.career_interview_states
                SET state = $3::jsonb,
                    state_version = state_version + 1,
                    updated_at = NOW()
                WHERE session_id = $1::uuid AND candidate_id = $2::uuid
                """,
                session_id,
                candidate_id,
                json.dumps(updated.model_dump(mode="json")),
            )
            await db.execute(
                """
                INSERT INTO public.messages
                  (id, conversation_id, role, content, content_type, voice_session_id)
                VALUES ($1::uuid, $2::uuid, 'user', $3, $4, $5::uuid)
                """,
                message_id,
                conversation_id,
                content,
                content_type,
                session_id,
            )

    if expired:
        raise CareerInterviewExpiredError

    return CareerInterviewTurn(
        coverage=updated,
        focus=next_focus.topic,
        prompt_hint=next_focus.prompt_hint,
        should_wrap=next_focus.should_wrap,
        state_version=state_version,
    )


def _is_explicit_refusal(answer: str) -> bool:
    refusal_candidate = _NEGATED_SKIP_PATTERN.sub("", answer)
    if _WANT_TO_REFUSAL_PATTERN.fullmatch(refusal_candidate) and not _has_meaningful_continuation(
        refusal_candidate
    ):
        return True
    if _PREFER_NOT_REFUSAL_PATTERN.search(refusal_candidate):
        return not _has_meaningful_continuation(refusal_candidate)
    return _SKIP_REFUSAL_PATTERN.search(refusal_candidate) is not None


def _has_meaningful_continuation(answer: str) -> bool:
    for match in _CONTINUATION_PATTERN.finditer(answer):
        detail = match.group("detail")
        if _SUBSTANTIVE_FACT_PATTERN.search(detail):
            return True
        if _NON_ANSWER_PATTERN.search(detail):
            continue
        detail_words = re.findall(r"[a-z']+", detail)
        if any(word not in _CONTRAST_FILLER_WORDS for word in detail_words):
            return True
    return False


def _is_standalone_non_answer(answer: str) -> bool:
    if not _NON_ANSWER_PATTERN.search(answer):
        return False
    if _SUBSTANTIVE_FACT_PATTERN.search(answer) or _has_meaningful_continuation(answer):
        return False
    return True


def select_next_focus(
    state: CareerInterviewCoverage,
    *,
    elapsed_seconds: int | float,
) -> NextInterviewFocus:
    """Choose the next uncovered, non-declined topic or wrap the interview."""
    if elapsed_seconds >= 14 * 60:
        return NextInterviewFocus(topic=None, prompt_hint=_WRAP_HINT, should_wrap=True)

    unavailable = set(state.covered_topics) | set(state.declined_topics)
    for topic in INTERVIEW_TOPIC_PRIORITY:
        if topic not in unavailable:
            return NextInterviewFocus(topic=topic, prompt_hint=PROMPT_HINTS[topic])

    return NextInterviewFocus(topic=None, prompt_hint=_WRAP_HINT, should_wrap=True)


def record_candidate_answer(
    state: CareerInterviewCoverage,
    answer: str,
) -> CareerInterviewCoverage:
    """Return new coverage state after evaluating an answer to the current focus."""
    updated = state.model_copy(deep=True)
    updated.turn_count += 1

    topic = updated.current_focus
    if topic is None:
        return updated

    normalized_answer = answer.casefold()
    if _is_explicit_refusal(normalized_answer):
        if topic not in updated.declined_topics:
            updated.declined_topics.append(topic)
        return updated

    is_non_answer = _is_standalone_non_answer(normalized_answer)
    if not is_non_answer and len(answer.split()) >= 3 and topic not in updated.covered_topics:
        updated.covered_topics.append(topic)

    return updated
