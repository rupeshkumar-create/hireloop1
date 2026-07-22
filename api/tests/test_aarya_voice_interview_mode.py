"""Safety and persistence tests for Aarya's private career interview mode."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from hireloop_api.agents.aarya import agent as aarya_agent
from hireloop_api.agents.aarya.agent import (
    _career_interview_prompt_from_state,
    blocked_career_interview_mutation,
    build_career_interview_prompt,
)
from hireloop_api.config import Settings
from hireloop_api.models.career_interview import CareerInterviewCoverage, InterviewTopic
from hireloop_api.routes import chat as chat_routes
from hireloop_api.routes.chat import (
    SendMessageRequest,
    _memory_update_background,
    _persist_assistant_reply,
    load_prompt_history,
    load_recent_ordinary_assistant,
    prepare_career_interview_turn,
    resolve_chat_turn_routing,
)
from hireloop_api.services import career_interview
from hireloop_api.services.career_interview import (
    load_active_interview,
    record_turn_and_select_focus,
)
from hireloop_api.services.chat_sessions import load_candidate_chat_messages
from hireloop_api.services.memory import run_memory_update

MIGRATION = (
    Path(__file__).parents[2] / "supabase/migrations/20260721150000_aarya_career_call_phase1.sql"
)


class _Transaction:
    def __init__(self, db: InterviewDb) -> None:
        self.db = db

    async def __aenter__(self) -> None:
        self.db.in_transaction = True
        return None

    async def __aexit__(self, *args: object) -> None:
        self.db.transaction_error = args[0]
        self.db.in_transaction = False
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
        self.fail_message_insert = False
        self.in_transaction = False
        self.transaction_error: object = None
        self.session_status = "active"
        self.completion_reason: str | None = None
        self.duration_secs: int | None = None

    def transaction(self) -> _Transaction:
        return _Transaction(self)

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
            "db_now": datetime.now(UTC),
            "state": self.state,
            "state_version": self.state_version,
        }

    async def execute(self, query: str, *args: object) -> str:
        assert self.in_transaction
        normalized = " ".join(query.split())
        self.execute_calls.append((normalized, args))
        if "UPDATE public.voice_sessions" in normalized:
            self.session_status = "completed"
            self.completion_reason = "time_limit"
            self.duration_secs = 900
            return "UPDATE 1"
        if "UPDATE public.career_interview_states" in normalized:
            self.state = str(args[2])
            self.state_version += 1
            return "UPDATE 1"
        if "INSERT INTO public.messages" in normalized:
            if self.fail_message_insert:
                raise RuntimeError("message insert failed")
            return "INSERT 0 1"
        raise AssertionError(f"Unexpected execute: {normalized}")


class CapturingChatModel:
    instances: ClassVar[list[CapturingChatModel]] = []

    def __init__(self, **_kwargs: object) -> None:
        self.bound = False
        self.invocations: list[list[object]] = []
        self.instances.append(self)

    def bind_tools(self, _tools: object) -> CapturingChatModel:
        self.bound = True
        return self

    async def ainvoke(self, messages: list[object]) -> AIMessage:
        self.invocations.append(messages)
        return AIMessage(content="Thanks for sharing. What kind of impact did that work have?")


class _Acquire:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    async def __aenter__(self) -> object:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


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
    advisory = {"error": "Profile changes from this private call require candidate review."}

    assert (
        blocked_career_interview_mutation(tool_name="update_profile", career_interview_mode=True)
        == advisory
    )
    assert (
        blocked_career_interview_mutation(
            tool_name="update_job_preferences", career_interview_mode=True
        )
        == advisory
    )
    assert (
        blocked_career_interview_mutation(tool_name="profile_read", career_interview_mode=True)
        is None
    )
    assert (
        blocked_career_interview_mutation(tool_name="update_profile", career_interview_mode=False)
        is None
    )


@pytest.mark.parametrize(
    "answer",
    [
        "I want a remote product role in Bengaluru.",
        "Please show me jobs and apply to job 11111111-1111-1111-1111-111111111111.",
    ],
)
def test_private_interview_answers_stay_on_prompt_path_without_job_routing(answer: str) -> None:
    body = SendMessageRequest(
        content=answer,
        content_type="voice",
        voice_session_id=uuid4(),
    )

    routing = resolve_chat_turn_routing(body, career_interview_mode=True)
    prompt = _career_interview_prompt_from_state(
        {
            "messages": [HumanMessage(content=answer)],
            "career_interview_mode": True,
            "career_interview_focus": InterviewTopic.TARGET_ROLES,
            "career_interview_prompt_hint": "Ask which responsibilities they want next.",
            "career_interview_should_wrap": False,
        }
    )

    assert routing.normal_routing_enabled is False
    assert routing.user_intent == "general"
    assert routing.application_kit_job_ids == []
    assert prompt is not None
    assert "Private career interview mode is active" in prompt
    assert "target_roles" in prompt


@pytest.mark.asyncio
async def test_graph_uses_tool_free_private_prompt_for_job_like_interview_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    CapturingChatModel.instances = []
    monkeypatch.setattr(aarya_agent, "ChatOpenAI", CapturingChatModel)
    graph = aarya_agent.build_aarya_graph(
        Settings(_env_file=None, environment="development")  # type: ignore[call-arg]
    )

    await graph.ainvoke(
        {
            "messages": [
                HumanMessage(content="I want remote product roles and would apply to fintech jobs.")
            ],
            "user_id": str(uuid4()),
            "session_id": str(uuid4()),
            "action_count": 0,
            "tool_rounds": 0,
            "voice_mode": True,
            "career_interview_mode": True,
            "career_interview_focus": InterviewTopic.TARGET_ROLES,
            "career_interview_prompt_hint": "Ask which responsibilities they want next.",
            "career_interview_should_wrap": False,
        },
        config={"configurable": {"db": object()}},
    )

    invoked = [instance for instance in CapturingChatModel.instances if instance.invocations]
    assert len(invoked) == 1
    assert invoked[0].bound is False
    system_prompt = next(
        message.content
        for message in invoked[0].invocations[0]
        if isinstance(message, SystemMessage)
    )
    assert "Private career interview mode is active" in system_prompt
    assert "likely_intent: job_search" not in system_prompt


def test_private_interview_background_does_not_run_memory_extraction() -> None:
    settings = object()

    assert (
        _memory_update_background(
            settings=settings,
            candidate_id="candidate",
            conversation_id="conversation",
            career_interview_mode=True,
        )
        is None
    )
    ordinary = _memory_update_background(
        settings=settings,
        candidate_id="candidate",
        conversation_id="conversation",
        career_interview_mode=False,
    )
    assert ordinary is not None
    assert ordinary.func is run_memory_update


def test_migration_durably_attributes_messages_to_voice_sessions() -> None:
    sql = MIGRATION.read_text()

    assert "ADD COLUMN IF NOT EXISTS voice_session_id UUID" in sql
    assert "voice_sessions_id_conversation_unique" in sql
    assert "messages_voice_session_conversation_fk" in sql
    assert "FOREIGN KEY (voice_session_id, conversation_id)" in sql
    assert "REFERENCES public.voice_sessions(id, conversation_id) ON DELETE CASCADE" in sql
    assert "idx_messages_voice_session" in sql
    assert "WHERE voice_session_id IS NOT NULL" in sql


@pytest.mark.asyncio
async def test_assistant_persistence_is_idempotent_by_message_id_not_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = AsyncMock()
    voice_session_id = uuid4()
    conversation_id = uuid4()
    first_message_id = uuid4()
    second_message_id = uuid4()
    monkeypatch.setattr(chat_routes, "get_db_pool", AsyncMock(return_value=_Pool(db)))
    for message_id in (first_message_id, first_message_id, second_message_id):
        await _persist_assistant_reply(
            object(),  # type: ignore[arg-type]
            str(conversation_id),
            "Identical reply text",
            "private title",
            assistant_message_id=message_id,
            voice_session_id=voice_session_id,
        )

    db.fetchrow.assert_not_awaited()
    inserts = [
        call for call in db.execute.await_args_list if "INSERT INTO public.messages" in call.args[0]
    ]
    assert len(inserts) == 3
    assert all("ON CONFLICT (id) DO NOTHING" in call.args[0] for call in inserts)
    assert [call.args[1] for call in inserts] == [
        first_message_id,
        first_message_id,
        second_message_id,
    ]
    assert all(call.args[-1] == voice_session_id for call in inserts)


@pytest.mark.asyncio
async def test_prompt_history_isolates_private_and_ordinary_transcripts() -> None:
    db = AsyncMock()
    db.fetch.return_value = []
    conversation_id = uuid4()
    voice_session_id = uuid4()

    await load_prompt_history(db, conversation_id, voice_session_id=None)
    ordinary_sql, *ordinary_args = db.fetch.await_args.args
    assert "voice_session_id IS NULL" in ordinary_sql
    assert ordinary_args == [conversation_id]

    await load_prompt_history(db, conversation_id, voice_session_id=voice_session_id)
    private_sql, *private_args = db.fetch.await_args.args
    assert "voice_session_id = $2::uuid" in private_sql
    assert private_args == [conversation_id, voice_session_id]
    assert "IS NULL" not in private_sql


@pytest.mark.asyncio
async def test_career_path_recent_assistant_lookup_excludes_private_messages() -> None:
    db = AsyncMock()
    db.fetchrow.return_value = {"content": "ordinary reply"}

    result = await load_recent_ordinary_assistant(db, uuid4())

    sql = db.fetchrow.await_args.args[0]
    assert "voice_session_id IS NULL" in sql
    assert result == "ordinary reply"


@pytest.mark.asyncio
async def test_memory_source_excludes_private_voice_session_messages() -> None:
    db = AsyncMock()
    db.fetch.return_value = []

    await load_candidate_chat_messages(db, str(uuid4()))

    sql = db.fetch.await_args.args[0]
    assert "m.voice_session_id IS NULL" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("state_as_json", [False, True])
async def test_record_turn_parses_jsonb_state_and_advances_focus(state_as_json: bool) -> None:
    db = InterviewDb(state_as_json=state_as_json)

    turn = await record_turn_and_select_focus(
        db,
        session_id=db.session_id,
        candidate_id=db.candidate_id,
        conversation_id=db.conversation_id,
        message_id=uuid4(),
        content="I lead platform engineering at a fintech company.",
        content_type="voice",
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
    assert "FOR UPDATE OF vs, cis" in db.fetch_queries[0]
    assert "UPDATE public.career_interview_states" in db.execute_calls[0][0]
    assert "INSERT INTO public.messages" in db.execute_calls[1][0]
    assert db.execute_calls[1][1][-1] == db.session_id


@pytest.mark.asyncio
async def test_repeated_uncovered_focus_is_recorded_in_question_history() -> None:
    db = InterviewDb()

    turn = await record_turn_and_select_focus(
        db,
        session_id=db.session_id,
        candidate_id=db.candidate_id,
        conversation_id=db.conversation_id,
        message_id=uuid4(),
        content="I'm not sure.",
        content_type="voice",
    )

    assert turn.focus is InterviewTopic.CURRENT_WORK
    assert turn.coverage.question_history == [
        InterviewTopic.CURRENT_WORK,
        InterviewTopic.CURRENT_WORK,
    ]


@pytest.mark.asyncio
async def test_private_message_insert_failure_aborts_the_locked_state_transaction() -> None:
    db = InterviewDb()
    db.fail_message_insert = True

    with pytest.raises(RuntimeError, match="message insert failed"):
        await record_turn_and_select_focus(
            db,
            session_id=db.session_id,
            candidate_id=db.candidate_id,
            conversation_id=db.conversation_id,
            message_id=uuid4(),
            content="A private answer",
            content_type="voice",
        )

    assert db.transaction_error is RuntimeError
    assert [call[0].split()[0] for call in db.execute_calls] == ["UPDATE", "INSERT"]


@pytest.mark.asyncio
async def test_expired_turn_completes_call_without_advancing_state_or_message() -> None:
    db = InterviewDb()
    db.started_at = datetime.now(UTC) - timedelta(minutes=16)
    original_state = db.state
    original_version = db.state_version

    with pytest.raises(career_interview.CareerInterviewExpiredError):
        await record_turn_and_select_focus(
            db,
            session_id=db.session_id,
            candidate_id=db.candidate_id,
            conversation_id=db.conversation_id,
            message_id=uuid4(),
            content="This answer arrived after the call deadline.",
            content_type="voice",
        )

    assert db.session_status == "completed"
    assert db.completion_reason == "time_limit"
    assert db.duration_secs == 900
    assert db.state == original_state
    assert db.state_version == original_version
    assert len(db.execute_calls) == 1
    assert "WHERE id = $1::uuid" in db.execute_calls[0][0]
    assert "status = 'active'" in db.execute_calls[0][0]
    assert db.transaction_error is None


@pytest.mark.asyncio
async def test_expired_turn_maps_to_distinct_chat_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reject_expired(*_args: object, **_kwargs: object) -> None:
        raise career_interview.CareerInterviewExpiredError

    monkeypatch.setattr(chat_routes, "record_turn_and_select_focus", reject_expired)
    db = InterviewDb()

    with pytest.raises(HTTPException) as exc:
        await prepare_career_interview_turn(
            db=db,
            message_id=uuid4(),
            body=SendMessageRequest(
                content="A late answer",
                content_type="voice",
                voice_session_id=db.session_id,
            ),
            candidate_id=db.candidate_id,
            conversation_id=db.conversation_id,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Career call reached its 15-minute limit"


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
            message_id=uuid4(),
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
        message_id=uuid4(),
        body=SendMessageRequest(content="Hello Aarya", content_type="voice"),
        candidate_id=db.candidate_id,
        conversation_id=db.conversation_id,
    )

    assert turn is None
    assert db.fetch_queries == []
