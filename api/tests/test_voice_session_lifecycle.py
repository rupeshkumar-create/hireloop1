from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from hireloop_api.routes import voice_sessions

MIGRATION = (
    Path(__file__).parents[2] / "supabase/migrations/20260721150000_aarya_career_call_phase1.sql"
)


class _Transaction:
    def __init__(self, db: LifecycleDb) -> None:
        self.db = db

    async def __aenter__(self) -> None:
        self.db.in_transaction = True

    async def __aexit__(self, *args: object) -> None:
        self.db.in_transaction = False


class LifecycleDb:
    def __init__(self, state: str) -> None:
        self.user_id = uuid.uuid4()
        self.candidate_id = uuid.uuid4()
        self.conversation_id = uuid.uuid4()
        self.other_conversation_id = uuid.uuid4()
        self.session_id = uuid.uuid4()
        self.state = state
        self.status = "scheduled" if state == "scheduled" else "active"
        self.conversation_deleted = False
        self.wrong_conversation_owner = False
        self.wrong_session_owner = False
        self.inserted_voice_session = False
        self.in_transaction = False
        self.raise_unique_on_insert = False
        self.consent_version: str | None = "career-call-v1"
        self.has_interview_state = True
        self.has_consent_audit = True
        self.consent_audit_created_at = datetime(2099, 7, 23, 5, tzinfo=UTC)
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    @classmethod
    def new_candidate(cls) -> LifecycleDb:
        return cls("new")

    @classmethod
    def scheduled_call(cls) -> LifecycleDb:
        return cls("scheduled")

    @classmethod
    def active_call(cls) -> LifecycleDb:
        return cls("active")

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def _session_row(self) -> dict[str, object]:
        return {
            "id": self.session_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "scheduled_at": datetime(2099, 7, 23, 5, tzinfo=UTC),
            "started_at": datetime(2099, 7, 23, 5, tzinfo=UTC),
            "created_at": datetime(2099, 7, 23, 4, 55, tzinfo=UTC),
            "duration_secs": 42,
            "completion_reason": "candidate_ended" if self.status == "completed" else None,
            "consent_version": self.consent_version,
            "has_interview_state": self.has_interview_state,
            "has_consent_audit": self.has_consent_audit,
        }

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        normalized = " ".join(query.split())
        self.fetchrow_calls.append((normalized, args))
        if "FROM public.candidates" in normalized and "user_id" in normalized:
            return {"id": self.candidate_id}
        if "FROM public.conversations" in normalized:
            if self.conversation_deleted or self.wrong_conversation_owner:
                return None
            return {"id": self.conversation_id}
        if "AS has_interview_state" in normalized:
            audit_is_current = self.has_consent_audit
            if "cl.created_at >=" in normalized:
                audit_is_current = audit_is_current and self.consent_audit_created_at >= args[4]
            return {
                "has_interview_state": self.has_interview_state,
                "has_consent_audit": audit_is_current,
            }
        if "FROM public.voice_sessions vs" in normalized and "status = 'active'" in normalized:
            if self.state == "active":
                return self._session_row()
            return None
        if "status = 'active'" in normalized and "FOR UPDATE" not in normalized:
            if self.state in {"active", "completed"}:
                return self._session_row()
            return None
        if "status = 'scheduled'" in normalized and "FOR UPDATE" in normalized:
            if self.state == "scheduled" and not self.wrong_session_owner:
                return self._session_row()
            return None
        if "FROM public.voice_sessions" in normalized and "FOR UPDATE" in normalized:
            if self.wrong_session_owner:
                return None
            if self.state in {"scheduled", "active", "completed"}:
                return self._session_row()
            return None
        if "FROM public.messages" in normalized:
            return {"content": "Aarya's existing private recap."}
        raise AssertionError(f"Unrecognised fetchrow query: {normalized}")

    async def execute(self, query: str, *args: object) -> str:
        assert self.in_transaction, "lifecycle writes must be transactional"
        normalized = " ".join(query.split())
        self.execute_calls.append((normalized, args))
        if "INSERT INTO public.voice_sessions" in normalized:
            if self.raise_unique_on_insert:
                self.state = "active"
                self.status = "active"
                raise asyncpg.UniqueViolationError("active career call race")
            self.inserted_voice_session = True
            self.session_id = args[0]  # type: ignore[assignment]
            self.status = "active"
            self.state = "active"
            return "INSERT 0 1"
        if "UPDATE public.voice_sessions" in normalized:
            if "SET status = 'completed'" in normalized:
                self.status = "completed"
                self.state = "completed"
            elif "SET status = 'active'" in normalized:
                self.status = "active"
                self.state = "active"
            elif "SET consent_version" in normalized:
                self.consent_version = str(args[2])
            return "UPDATE 1"
        if "INSERT INTO public.consent_log" in normalized:
            self.has_consent_audit = True
            return "INSERT 0 1"
        if "INSERT INTO public.career_interview_states" in normalized:
            self.has_interview_state = True
            return "INSERT 0 1"
        if "UPDATE public.career_interview_states" in normalized:
            return "UPDATE 1"
        raise AssertionError(f"Unrecognised execute query: {normalized}")


def _start_request(**overrides: object) -> object:
    values = {"conversation_id": uuid.uuid4(), "consent": True, **overrides}
    return voice_sessions.StartCareerCallRequest(**values)


def _complete_request(**overrides: object) -> object:
    values = {
        "completion_reason": "candidate_ended",
        "duration_seconds": 42,
        **overrides,
    }
    return voice_sessions.CompleteCareerCallRequest(**values)


def test_career_call_migration_has_lifecycle_and_rls_contract() -> None:
    sql = MIGRATION.read_text()
    assert "conversation_id UUID" in sql
    assert "consent_version TEXT" in sql
    assert "completion_reason TEXT" in sql
    assert "CREATE TABLE public.career_interview_states" in sql
    assert "ALTER TABLE public.career_interview_states ENABLE ROW LEVEL SECURITY" in sql
    assert 'CREATE POLICY "career_interview_states: candidate read own"' in sql
    assert "recording_url IS NULL" in sql
    assert "conversations_id_candidate_unique" in sql
    assert "voice_sessions_id_candidate_unique" in sql


@pytest.mark.asyncio
async def test_start_instant_call_requires_consent() -> None:
    db = LifecycleDb.new_candidate()
    with pytest.raises(HTTPException) as exc:
        await voice_sessions.start_career_call(
            _start_request(conversation_id=db.conversation_id, consent=False),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 400
    assert db.execute_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted,wrong_owner", [(True, False), (False, True)])
async def test_start_enforces_conversation_ownership_and_soft_delete(
    deleted: bool, wrong_owner: bool
) -> None:
    db = LifecycleDb.new_candidate()
    db.conversation_deleted = deleted
    db.wrong_conversation_owner = wrong_owner
    with pytest.raises(HTTPException) as exc:
        await voice_sessions.start_career_call(
            _start_request(conversation_id=db.conversation_id),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_start_scheduled_call_updates_same_row() -> None:
    db = LifecycleDb.scheduled_call()
    out = await voice_sessions.start_career_call(
        _start_request(
            scheduled_session_id=db.session_id,
            conversation_id=db.conversation_id,
        ),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    assert out.id == str(db.session_id)
    assert db.inserted_voice_session is False
    assert db.status == "active"


@pytest.mark.asyncio
async def test_start_is_idempotent_for_same_active_conversation() -> None:
    db = LifecycleDb.active_call()
    out = await voice_sessions.start_career_call(
        _start_request(conversation_id=db.conversation_id),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    assert out.id == str(db.session_id)
    assert db.execute_calls == []


@pytest.mark.asyncio
async def test_start_rejects_active_same_conversation_with_different_consent_version() -> None:
    db = LifecycleDb.active_call()
    with pytest.raises(HTTPException) as exc:
        await voice_sessions.start_career_call(
            _start_request(
                conversation_id=db.conversation_id,
                consent_version="career-call-v2",
            ),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 409
    assert db.execute_calls == []


@pytest.mark.asyncio
async def test_start_does_not_reuse_prior_call_consent_audit() -> None:
    db = LifecycleDb.active_call()
    db.consent_audit_created_at = datetime(2099, 7, 23, 4, 59, tzinfo=UTC)

    await voice_sessions.start_career_call(
        _start_request(conversation_id=db.conversation_id),
        current_user={"id": str(db.user_id)},
        db=db,
    )

    consent_writes = [call for call in db.execute_calls if "consent_log" in call[0]]
    assert len(consent_writes) == 1


@pytest.mark.asyncio
async def test_start_reuses_current_call_consent_audit_without_writes() -> None:
    db = LifecycleDb.active_call()
    db.consent_audit_created_at = datetime(2099, 7, 23, 5, 0, 1, tzinfo=UTC)

    await voice_sessions.start_career_call(
        _start_request(conversation_id=db.conversation_id),
        current_user={"id": str(db.user_id)},
        db=db,
    )

    assert db.execute_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing_version,missing_state,missing_audit",
    [
        (None, True, False),
        ("career-call-v1", False, True),
        (None, True, True),
        ("career-call-v1", True, True),
    ],
)
async def test_start_recovers_legacy_active_call_transactionally(
    existing_version: str | None,
    missing_state: bool,
    missing_audit: bool,
) -> None:
    db = LifecycleDb.active_call()
    db.consent_version = existing_version
    db.has_interview_state = not missing_state
    db.has_consent_audit = not missing_audit

    first = await voice_sessions.start_career_call(
        _start_request(conversation_id=db.conversation_id),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    writes_after_recovery = len(db.execute_calls)
    second = await voice_sessions.start_career_call(
        _start_request(conversation_id=db.conversation_id),
        current_user={"id": str(db.user_id)},
        db=db,
    )

    assert first == second
    assert db.consent_version == "career-call-v1"
    assert db.has_interview_state is True
    assert db.has_consent_audit is True
    assert len(db.execute_calls) == writes_after_recovery
    active_queries = [sql for sql, _ in db.fetchrow_calls if "status = 'active'" in sql]
    flag_queries = [sql for sql, _ in db.fetchrow_calls if "AS has_interview_state" in sql]
    assert active_queries
    assert all("FOR UPDATE" in sql for sql in active_queries)
    assert flag_queries
    lock_index = next(i for i, (sql, _) in enumerate(db.fetchrow_calls) if sql == active_queries[0])
    flag_index = next(i for i, (sql, _) in enumerate(db.fetchrow_calls) if sql == flag_queries[0])
    assert lock_index < flag_index
    state_inserts = [sql for sql, _ in db.execute_calls if "career_interview_states" in sql]
    if missing_state:
        assert state_inserts and all("ON CONFLICT" in sql for sql in state_inserts)


@pytest.mark.asyncio
async def test_start_rejects_active_different_conversation() -> None:
    db = LifecycleDb.active_call()
    with pytest.raises(HTTPException) as exc:
        await voice_sessions.start_career_call(
            _start_request(conversation_id=db.other_conversation_id),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("same_conversation", [True, False])
async def test_start_handles_unique_active_call_race(same_conversation: bool) -> None:
    db = LifecycleDb.new_candidate()
    db.raise_unique_on_insert = True
    requested_conversation = db.conversation_id if same_conversation else db.other_conversation_id

    if same_conversation:
        out = await voice_sessions.start_career_call(
            _start_request(conversation_id=requested_conversation),
            current_user={"id": str(db.user_id)},
            db=db,
        )
        assert out.id == str(db.session_id)
        assert out.status == "active"
    else:
        with pytest.raises(HTTPException) as exc:
            await voice_sessions.start_career_call(
                _start_request(conversation_id=requested_conversation),
                current_user={"id": str(db.user_id)},
                db=db,
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_start_writes_consent_and_initial_coverage_transactionally() -> None:
    db = LifecycleDb.new_candidate()
    await voice_sessions.start_career_call(
        _start_request(conversation_id=db.conversation_id, consent_version="career-call-v2"),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    consent_call = next(call for call in db.execute_calls if "consent_log" in call[0])
    assert consent_call[1][1] == "voice_career_discovery:career-call-v2"
    state_call = next(call for call in db.execute_calls if "career_interview_states" in call[0])
    state = json.loads(str(state_call[1][2]))
    assert state["current_focus"] == "current_work"
    assert state["question_history"] == ["current_work"]


@pytest.mark.asyncio
async def test_complete_updates_session_and_state_without_candidate_profile() -> None:
    db = LifecycleDb.active_call()
    out = await voice_sessions.complete_career_call(
        db.session_id,
        _complete_request(),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    assert out.status == "completed"
    assert any("transcript_version = transcript_version + 1" in sql for sql, _ in db.execute_calls)
    assert any("UPDATE public.career_interview_states" in sql for sql, _ in db.execute_calls)
    assert all("UPDATE public.candidates" not in sql for sql, _ in db.execute_calls)


@pytest.mark.asyncio
async def test_complete_enforces_ownership() -> None:
    db = LifecycleDb.active_call()
    db.wrong_session_owner = True
    with pytest.raises(HTTPException) as exc:
        await voice_sessions.complete_career_call(
            db.session_id,
            _complete_request(),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_repeat_identical_completion_is_idempotent() -> None:
    db = LifecycleDb.active_call()
    first = await voice_sessions.complete_career_call(
        db.session_id,
        _complete_request(),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    writes_after_first = len(db.execute_calls)

    second = await voice_sessions.complete_career_call(
        db.session_id,
        _complete_request(),
        current_user={"id": str(db.user_id)},
        db=db,
    )

    assert second == first
    assert len(db.execute_calls) == writes_after_first


@pytest.mark.asyncio
async def test_conflicting_repeat_completion_returns_409_without_writes() -> None:
    db = LifecycleDb.active_call()
    await voice_sessions.complete_career_call(
        db.session_id,
        _complete_request(),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    writes_after_first = len(db.execute_calls)

    with pytest.raises(HTTPException) as exc:
        await voice_sessions.complete_career_call(
            db.session_id,
            _complete_request(duration_seconds=43),
            current_user={"id": str(db.user_id)},
            db=db,
        )

    assert exc.value.status_code == 409
    assert len(db.execute_calls) == writes_after_first
    assert all("UPDATE public.candidates" not in sql for sql, _ in db.execute_calls)


@pytest.mark.asyncio
async def test_complete_rejects_non_active_session_without_profile_mutation() -> None:
    db = LifecycleDb.scheduled_call()
    with pytest.raises(HTTPException) as exc:
        await voice_sessions.complete_career_call(
            db.session_id,
            _complete_request(),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 409
    assert all("UPDATE public.candidates" not in sql for sql, _ in db.execute_calls)


@pytest.mark.parametrize("duration", [-1, 961])
def test_complete_enforces_duration_bounds(duration: int) -> None:
    with pytest.raises(ValidationError):
        _complete_request(duration_seconds=duration)
