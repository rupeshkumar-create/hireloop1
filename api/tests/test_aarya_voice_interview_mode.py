"""Safety and persistence tests for Aarya's private career interview mode."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from hireloop_api.agents.aarya.agent import (
    blocked_career_interview_mutation,
    build_career_interview_prompt,
)
from hireloop_api.models.career_interview import CareerInterviewCoverage, InterviewTopic
from hireloop_api.routes.chat import SendMessageRequest, prepare_career_interview_turn
from hireloop_api.services.career_interview import (
    load_active_interview,
    record_turn_and_select_focus,
)


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class InterviewDb:
    def __init__(self, *, state_as_json: bool = False) -> None:
        self.session_id = uuid4()
        self.candidate_id = uuid4()
        self.conversation_id = uuid4()
        self.started_at = datetime.now(UTC) - timedelta(seconds=75)
        state = CareerInterviewCoverage(
            current_focus=InterviewTopic.CURRENT_WORK,
            question_history=[InterviewTopic.CURRENT_WORK],
        ).model_dump(mode="json")
        self.state: dict[str, Any] | str = json.dumps(state) if state_as_json else state
        self.state_version = 3
        self.fetch_queries: list[str] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        normalized = " ".join(query.split())
        self.fetch_queries.append(normalized)
        session_id, candidate_id = args[:2]
        if session_id != self.session_id or candidate_id != self.candidate_id:
            return None
        return {
            "session_id": self.session_id,
            "candidate_id": self.candidate_id,
            "conversation_id": self.conversation_id,
            "started_at": self.started_at,
            "state": self.state,
            "state_version": self.state_version,
        }

    async def execute(self, query: str, *args: object) -> str:
        normalized = " ".join(query.split())
        self.execute_calls.append((normalized, args))
        self.state = str(args[2])
        self.state_version += 1
        return "UPDATE 1"


def test_career_interview_prompt_is_single_question_private_discovery_guidance() -> None:
    prompt = build_career_interview_prompt(
        focus=InterviewTopic.SKILLS,
        prompt_hint="Ask which skills they use most.",
        should_wrap=False,
    )

    assert "skills" in prompt
    assert "Ask which skills they use most." in prompt
    assert "exactly one natural follow-up question" in prompt
    assert "acknowledge" in prompt
    assert "Do not update the candidate profile or job preferences" in prompt
    for protected_trait in (
        "age",
        "gender",
        "religion",
        "caste",
        "disability",
        "family status",
        "accent",
        "emotion",
        "personality",
    ):
        assert protected_trait in prompt


def test_career_interview_prompt_has_explicit_wrap_up_guidance() -> None:
    prompt = build_career_interview_prompt(
        focus=None,
        prompt_hint="Recap what was learned and close warmly.",
        should_wrap=True,
    )

    assert "Wrap up now" in prompt
    assert "Do not ask another discovery question" in prompt


def test_private_interview_blocks_profile_and_preference_mutations_only() -> None:
    assert blocked_career_interview_mutation("update_profile", True)
    assert blocked_career_interview_mutation("update_job_preferences", True)
    assert not blocked_career_interview_mutation("profile_read", True)
    assert not blocked_career_interview_mutation("update_profile", False)


@pytest.mark.asyncio
@pytest.mark.parametrize("state_as_json", [False, True])
async def test_record_turn_parses_jsonb_state_and_advances_focus(state_as_json: bool) -> None:
    db = InterviewDb(state_as_json=state_as_json)

    turn = await record_turn_and_select_focus(
        db,
        session_id=db.session_id,
        candidate_id=db.candidate_id,
        conversation_id=db.conversation_id,
        answer="I lead platform engineering at a fintech company.",
    )

    assert turn.focus is InterviewTopic.IMPACT
    assert turn.coverage.covered_topics == [InterviewTopic.CURRENT_WORK]
    assert turn.coverage.question_history == [
        InterviewTopic.CURRENT_WORK,
        InterviewTopic.IMPACT,
    ]
    assert turn.state_version == 4
    persisted = json.loads(str(db.execute_calls[0][1][2]))
    assert persisted["current_focus"] == "impact"
    assert "FOR UPDATE OF cis" in db.fetch_queries[0]


@pytest.mark.asyncio
async def test_load_active_interview_requires_candidate_owned_active_career_call() -> None:
    db = InterviewDb()

    interview = await load_active_interview(db, db.session_id, db.candidate_id)
    missing = await load_active_interview(db, db.session_id, uuid4())

    assert interview is not None
    assert interview.conversation_id == db.conversation_id
    assert missing is None
    assert "vs.session_type = 'career_chat'" in db.fetch_queries[0]
    assert "vs.status = 'active'" in db.fetch_queries[0]
    assert "vs.conversation_id IS NOT NULL" in db.fetch_queries[0]
    assert "vs.started_at IS NOT NULL" in db.fetch_queries[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["wrong_candidate", "wrong_conversation", "inactive"])
async def test_private_interview_turn_rejects_mismatch_or_inactive_session(
    mode: str,
) -> None:
    db = InterviewDb()
    expected_conversation = uuid4() if mode == "wrong_conversation" else db.conversation_id
    candidate_id = uuid4() if mode == "wrong_candidate" else db.candidate_id
    if mode == "inactive":
        db.session_id = uuid4()

    with pytest.raises(HTTPException) as exc:
        await prepare_career_interview_turn(
            db=db,
            body=SendMessageRequest(
                content="My latest work was on payments.",
                content_type="voice",
                voice_session_id=uuid4() if mode == "inactive" else db.session_id,
            ),
            candidate_id=candidate_id,
            conversation_id=expected_conversation,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_ordinary_voice_turn_remains_backward_compatible() -> None:
    db = InterviewDb()

    turn = await prepare_career_interview_turn(
        db=db,
        body=SendMessageRequest(content="Hello Aarya", content_type="voice"),
        candidate_id=db.candidate_id,
        conversation_id=db.conversation_id,
    )

    assert turn is None
    assert db.fetch_queries == []
