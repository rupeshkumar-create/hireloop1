# Aarya Trustworthy Career Call — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a private, consented 15-minute Aarya career-discovery call that candidates can start immediately or schedule, with adaptive question coverage, one durable session lifecycle, interruption-safe transcript persistence, and no direct voice-derived profile mutation.

**Architecture:** Extend the existing Aarya master loop with a typed `CareerInterviewCoverage` state and deterministic next-focus policy. Keep transcript turns in the existing conversation tables, store session/coverage state in Postgres, and pass the active voice-session ID through the existing SSE chat request. Scheduled and instant calls share one lifecycle API; Google Calendar is optional reminder enrichment and never creates global capacity constraints.

**Tech Stack:** FastAPI, Python 3.12, Pydantic v2, asyncpg, Postgres/Supabase RLS, existing Postgres `background_jobs`, Next.js 15, strict TypeScript, Zod, Tailwind, Deepgram STT/TTS, OpenRouter through the existing Aarya LangGraph loop.

---

## Scope Boundary

This plan implements only Phase 1 from the approved design. It does not create
fact proposals, confirmed profile versions, job-specific screening, or recruiter
screening cards. Those belong to Phases 2 and 3. Phase 1 must remove the current
voice-to-profile write so unreviewed transcript extraction cannot become trusted
candidate data before Phase 2 exists.

Implementation should run in an isolated `codex/` worktree because the current
beta worktree contains unrelated user edits, including `PHASE_TRACKER.md` and the
Terms page. When bringing the branch back, preserve those edits and resolve only
the exact overlapping hunks with the user rather than overwriting either file.

## File Map

| File | Responsibility |
| --- | --- |
| `supabase/migrations/20260721150000_aarya_career_call_phase1.sql` | Session lifecycle columns, coverage table, indexes, RLS |
| `api/src/hireloop_api/models/career_interview.py` | Pydantic contracts for coverage, focus, and completion |
| `api/src/hireloop_api/services/career_interview.py` | Pure coverage policy plus DB repository functions |
| `api/src/hireloop_api/routes/voice_sessions.py` | Schedule/start/list/cancel/complete one session row |
| `api/src/hireloop_api/routes/voice.py` | Keep STT/TTS/WS only; compatibility completion delegates without profile mutation |
| `api/src/hireloop_api/routes/chat.py` | Validate active session, record coverage, inject interview context |
| `api/src/hireloop_api/agents/aarya/agent.py` | Career-interview prompt/state and mutation guard |
| `api/src/hireloop_api/services/google_calendar.py` | Fifteen-minute optional calendar event; no global availability semantics |
| `api/src/hireloop_api/services/notifications.py` | Reminder link targets the in-app scheduled session |
| `app/src/lib/api/voiceSessions.ts` | Zod-validated voice-session API client |
| `app/src/app/voice/VoiceSession.tsx` | Consent, lifecycle ID, timer, reconnect, and completion |
| `app/src/components/chat/VoiceDeepDiveModal.tsx` | Instant versus scheduled entry and active-session handoff |
| `app/src/components/dashboard/HomePanel.tsx` | Start-now and schedule-later actions |
| `api/tests/test_career_interview_policy.py` | Pure policy regression tests |
| `api/tests/test_voice_session_lifecycle.py` | Route lifecycle, ownership, consent, and no-profile-write tests |
| `api/tests/test_voice_booking.py` | Fifteen-minute and concurrent scheduling tests |
| `api/tests/test_aarya_voice_interview_mode.py` | Prompt and forbidden mutation tests |

### Task 1: Add the Phase 1 Database Contract

**Files:**
- Create: `supabase/migrations/20260721150000_aarya_career_call_phase1.sql`
- Test: `api/tests/test_voice_session_lifecycle.py`

- [ ] **Step 1: Write the migration contract test**

Create a test that reads the migration and proves the security- and lifecycle-
critical clauses exist:

```python
from pathlib import Path


MIGRATION = (
    Path(__file__).parents[2]
    / "supabase/migrations/20260721150000_aarya_career_call_phase1.sql"
)


def test_career_call_migration_has_lifecycle_and_rls_contract() -> None:
    sql = MIGRATION.read_text()
    assert "conversation_id UUID" in sql
    assert "consent_version TEXT" in sql
    assert "completion_reason TEXT" in sql
    assert "CREATE TABLE public.career_interview_states" in sql
    assert "ALTER TABLE public.career_interview_states ENABLE ROW LEVEL SECURITY" in sql
    assert 'CREATE POLICY "career_interview_states: candidate read own"' in sql
    assert "recording_url IS NULL" in sql
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd api && uv run pytest tests/test_voice_session_lifecycle.py::test_career_call_migration_has_lifecycle_and_rls_contract -v
```

Expected: FAIL because the migration file does not exist.

- [ ] **Step 3: Create the migration**

Use the following schema. Preserve the existing status enum values because
deployed rows already depend on them.

```sql
ALTER TABLE public.voice_sessions
  ADD COLUMN IF NOT EXISTS conversation_id UUID
    REFERENCES public.conversations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS consent_version TEXT,
  ADD COLUMN IF NOT EXISTS transcript_version INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS completion_reason TEXT
    CHECK (completion_reason IS NULL OR completion_reason IN (
      'candidate_ended', 'time_limit', 'coverage_complete',
      'interrupted', 'cancelled'
    )),
  ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'not_started'
    CHECK (extraction_status IN ('not_started', 'queued', 'processing', 'review_pending', 'failed'));

CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_sessions_active_candidate
  ON public.voice_sessions(candidate_id)
  WHERE session_type = 'career_chat' AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_voice_sessions_conversation
  ON public.voice_sessions(conversation_id)
  WHERE conversation_id IS NOT NULL;

CREATE TABLE public.career_interview_states (
  session_id UUID PRIMARY KEY
    REFERENCES public.voice_sessions(id) ON DELETE CASCADE,
  candidate_id UUID NOT NULL
    REFERENCES public.candidates(id) ON DELETE CASCADE,
  state JSONB NOT NULL,
  state_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER career_interview_states_updated_at
  BEFORE UPDATE ON public.career_interview_states
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_career_interview_states_candidate
  ON public.career_interview_states(candidate_id, updated_at DESC);

ALTER TABLE public.career_interview_states ENABLE ROW LEVEL SECURITY;

CREATE POLICY "career_interview_states: candidate read own"
  ON public.career_interview_states FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates
      WHERE user_id = auth.uid() AND deleted_at IS NULL
    )
  );

CREATE POLICY "career_interview_states: admin read all"
  ON public.career_interview_states FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.users
      WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
    )
  );

ALTER TABLE public.voice_sessions
  ADD CONSTRAINT voice_sessions_no_default_recording
  CHECK (recording_url IS NULL);
```

Before adding the last constraint, verify production has no non-null
`recording_url` rows. If any exist, stop and ask for a retention decision rather
than deleting them. Also verify there is at most one active `career_chat` row per
candidate before creating the partial unique index; reconcile duplicate active
rows explicitly instead of letting migration failure choose which row survives.

- [ ] **Step 4: Run the migration contract test and SQL lint check**

Run:

```bash
cd api && uv run pytest tests/test_voice_session_lifecycle.py::test_career_call_migration_has_lifecycle_and_rls_contract -v
git diff --check -- supabase/migrations/20260721150000_aarya_career_call_phase1.sql
```

Expected: PASS and no whitespace errors.

- [ ] **Step 5: Commit the schema contract**

```bash
git add supabase/migrations/20260721150000_aarya_career_call_phase1.sql api/tests/test_voice_session_lifecycle.py
git commit -m "feat: add trustworthy career call schema"
```

### Task 2: Build the Typed Interview Coverage Policy

**Files:**
- Create: `api/src/hireloop_api/models/career_interview.py`
- Create: `api/src/hireloop_api/services/career_interview.py`
- Create: `api/tests/test_career_interview_policy.py`

- [ ] **Step 1: Write failing policy tests**

```python
from hireloop_api.models.career_interview import CareerInterviewCoverage, InterviewTopic
from hireloop_api.services.career_interview import record_candidate_answer, select_next_focus


def test_next_focus_prefers_missing_high_value_topic() -> None:
    state = CareerInterviewCoverage()
    focus = select_next_focus(state, elapsed_seconds=60)
    assert focus.topic == InterviewTopic.CURRENT_WORK
    assert focus.should_wrap is False


def test_answer_marks_only_current_topic_covered() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.CURRENT_WORK)
    updated = record_candidate_answer(
        state,
        "I lead payment reconciliation services at my current company.",
    )
    assert InterviewTopic.CURRENT_WORK in updated.covered_topics
    assert updated.turn_count == 1


def test_declined_topic_is_not_reasked() -> None:
    state = CareerInterviewCoverage(current_focus=InterviewTopic.COMPENSATION)
    updated = record_candidate_answer(state, "I'd rather not discuss salary right now.")
    assert InterviewTopic.COMPENSATION in updated.declined_topics
    assert select_next_focus(updated, elapsed_seconds=300).topic != InterviewTopic.COMPENSATION


def test_policy_wraps_at_fourteen_minutes() -> None:
    state = CareerInterviewCoverage()
    focus = select_next_focus(state, elapsed_seconds=14 * 60)
    assert focus.should_wrap is True
    assert focus.topic is None
```

- [ ] **Step 2: Run tests and verify RED**

```bash
cd api && uv run pytest tests/test_career_interview_policy.py -v
```

Expected: collection FAIL because the modules do not exist.

- [ ] **Step 3: Implement Pydantic contracts**

```python
# api/src/hireloop_api/models/career_interview.py
from enum import StrEnum

from pydantic import BaseModel, Field


class InterviewTopic(StrEnum):
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
    schema_version: int = 1
    covered_topics: list[InterviewTopic] = Field(default_factory=list)
    declined_topics: list[InterviewTopic] = Field(default_factory=list)
    question_history: list[InterviewTopic] = Field(default_factory=list)
    current_focus: InterviewTopic | None = None
    turn_count: int = 0
    completion_reason: str | None = None


class NextInterviewFocus(BaseModel):
    topic: InterviewTopic | None
    prompt_hint: str
    should_wrap: bool = False


class ActiveCareerInterview(BaseModel):
    session_id: uuid.UUID
    candidate_id: uuid.UUID
    conversation_id: uuid.UUID
    started_at: datetime
    coverage: CareerInterviewCoverage
```

Add `import uuid` and `from datetime import datetime` to this model module.

- [ ] **Step 4: Implement the pure policy**

```python
# api/src/hireloop_api/services/career_interview.py
from hireloop_api.models.career_interview import (
    CareerInterviewCoverage,
    InterviewTopic,
    NextInterviewFocus,
)

_ORDER = (
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

_HINTS = {
    InterviewTopic.CURRENT_WORK: "Understand what they do now and what they personally own.",
    InterviewTopic.IMPACT: "Ask for one concrete project and what changed because of their work.",
    InterviewTopic.SKILLS: "Clarify tools used hands-on, depth, and recency.",
    InterviewTopic.TARGET_ROLES: "Clarify the role and seniority they want next.",
    InterviewTopic.LOCATION_SCOPE: "Clarify city, state, remote, relocation, or all-India scope.",
    InterviewTopic.WORK_MODE: "Clarify remote, hybrid, or on-site preference.",
    InterviewTopic.NOTICE_PERIOD: "Ask their current or expected notice period.",
    InterviewTopic.COMPENSATION: "Ask expected CTC only if they are comfortable sharing it.",
    InterviewTopic.RELOCATION: "Clarify willingness and constraints around relocation.",
    InterviewTopic.INDUSTRIES: "Clarify preferred or excluded industries.",
    InterviewTopic.LANGUAGES: "Ask only for languages and proficiency they choose to declare.",
    InterviewTopic.DEAL_BREAKERS: "Clarify company, role, shift, travel, or culture deal-breakers.",
}


def select_next_focus(
    state: CareerInterviewCoverage,
    *,
    elapsed_seconds: int,
) -> NextInterviewFocus:
    if elapsed_seconds >= 14 * 60:
        return NextInterviewFocus(
            topic=None,
            prompt_hint="Recap what you understood, identify any uncertainty, and close warmly.",
            should_wrap=True,
        )
    unavailable = set(state.covered_topics) | set(state.declined_topics)
    for topic in _ORDER:
        if topic not in unavailable:
            return NextInterviewFocus(topic=topic, prompt_hint=_HINTS[topic])
    return NextInterviewFocus(
        topic=None,
        prompt_hint="Recap the candidate's goals and close the call warmly.",
        should_wrap=True,
    )


def record_candidate_answer(
    state: CareerInterviewCoverage,
    answer: str,
) -> CareerInterviewCoverage:
    updated = state.model_copy(deep=True)
    updated.turn_count += 1
    focus = updated.current_focus
    if focus is None:
        return updated
    normalized = answer.strip().lower()
    declined = any(
        marker in normalized
        for marker in ("rather not", "prefer not", "don't want to", "skip this")
    )
    target = updated.declined_topics if declined else updated.covered_topics
    non_answers = ("don't know", "do not know", "not sure", "no idea")
    if (
        focus not in target
        and len(normalized.split()) >= 3
        and not any(marker in normalized for marker in non_answers)
    ):
        target.append(focus)
    return updated
```

- [ ] **Step 5: Run policy tests and Ruff**

```bash
cd api && uv run pytest tests/test_career_interview_policy.py -v
cd api && uv run ruff check src/hireloop_api/models/career_interview.py src/hireloop_api/services/career_interview.py tests/test_career_interview_policy.py
```

Expected: all tests PASS and Ruff exits zero.

- [ ] **Step 6: Commit the policy**

```bash
git add api/src/hireloop_api/models/career_interview.py api/src/hireloop_api/services/career_interview.py api/tests/test_career_interview_policy.py
git commit -m "feat: add Aarya interview coverage policy"
```

### Task 3: Unify Instant and Scheduled Session Lifecycle

**Files:**
- Modify: `api/src/hireloop_api/routes/voice_sessions.py`
- Modify: `api/src/hireloop_api/routes/voice.py`
- Modify: `api/src/hireloop_api/services/google_calendar.py`
- Modify: `api/tests/test_voice_booking.py`
- Modify: `api/tests/test_voice_session_lifecycle.py`
- Modify: `api/tests/test_voice_profile_enrichment.py`

- [ ] **Step 1: Replace global-slot tests with concurrent scheduling tests**

Change the duration assertion to 15 minutes and prove the route does not query
all candidates' bookings to suppress a requested time:

```python
def test_slots_are_15min_within_business_hours() -> None:
    now = _now_ist(2026, 6, 15, 7, 0)
    slots = generate_slots(days_ahead=0, now=now)
    assert slots
    assert all(
        datetime.fromisoformat(slot.end_time) - datetime.fromisoformat(slot.start_time)
        == timedelta(minutes=15)
        for slot in slots
    )


@pytest.mark.asyncio
async def test_booking_does_not_reject_same_time_for_another_candidate() -> None:
    db = BookingDb.for_candidate_with_other_candidate_booking()
    response = await book_session(
        BookSessionRequest(start_time="2026-07-23T05:00:00Z"),
        current_user={"id": str(db.user_id), "email": "candidate@example.com"},
        settings=Settings(_env_file=None, environment="test"),
        db=db,
    )
    assert response.start_time == "2026-07-23T05:00:00+00:00"
```

Add `BookingDb` to `test_voice_booking.py` as a complete async fake implementing
`fetchrow`, `execute`, and the calendar-token lookup used by `book_session`. Its
first candidate lookup returns the current candidate; it must raise the test if
the route issues the removed cross-candidate `scheduled_at = $1` clash query.

- [ ] **Step 2: Add failing lifecycle route tests**

Cover these exact behaviors:

```python
@pytest.mark.asyncio
async def test_start_instant_call_requires_consent() -> None:
    db = LifecycleDb.new_candidate()
    with pytest.raises(HTTPException) as exc:
        await start_career_call(
            StartCareerCallRequest(conversation_id=uuid.uuid4(), consent=False),
            current_user={"id": str(db.user_id)},
            db=db,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_start_scheduled_call_updates_same_row() -> None:
    db = LifecycleDb.scheduled_call()
    out = await start_career_call(
        StartCareerCallRequest(
            scheduled_session_id=db.session_id,
            conversation_id=db.conversation_id,
            consent=True,
        ),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    assert out.id == str(db.session_id)
    assert db.inserted_voice_session is False
    assert db.status == "active"


@pytest.mark.asyncio
async def test_complete_call_never_updates_candidate_profile() -> None:
    db = LifecycleDb.active_call()
    await complete_career_call(
        db.session_id,
        CompleteCareerCallRequest(completion_reason="candidate_ended"),
        current_user={"id": str(db.user_id)},
        db=db,
    )
    assert all("UPDATE public.candidates" not in sql for sql, _ in db.execute_calls)
```

Define `LifecycleDb` in the same test module with `new_candidate`,
`scheduled_call`, and `active_call` constructors plus async `fetchrow`, `fetchval`,
`execute`, and `transaction`. Record every SQL statement and argument, model the
candidate/conversation/session rows named by each constructor, and fail on any
unrecognised query so route tests cannot pass by silently returning `None`.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
cd api && uv run pytest tests/test_voice_booking.py tests/test_voice_session_lifecycle.py tests/test_voice_profile_enrichment.py -v
```

Expected: failures for 20-minute duration, missing lifecycle endpoints, and the
old direct profile update behavior.

- [ ] **Step 4: Implement lifecycle request/response models**

Add these Pydantic models in `voice_sessions.py`:

```python
class StartCareerCallRequest(BaseModel):
    conversation_id: uuid.UUID
    scheduled_session_id: uuid.UUID | None = None
    consent: bool
    consent_version: str = "career-call-v1"


class CareerCallResponse(BaseModel):
    id: str
    conversation_id: str
    status: str
    scheduled_at: str | None = None
    started_at: str | None = None


class CompleteCareerCallRequest(BaseModel):
    completion_reason: Literal[
        "candidate_ended", "time_limit", "coverage_complete", "interrupted"
    ]
    duration_seconds: int = Field(ge=0, le=16 * 60)
```

- [ ] **Step 5: Implement `POST /voice-sessions/start`**

The route must:

1. Reject `consent=False`.
2. Verify candidate ownership of the conversation.
3. Reuse the candidate's active career call when it has the same conversation.
4. If `scheduled_session_id` is present, lock and update that owned scheduled row.
5. Otherwise insert one active row.
6. Insert `consent_log(purpose='voice_career_discovery:career-call-v1')`.
7. Insert the initial `CareerInterviewCoverage` JSONB row with
   `current_focus='current_work'` and `question_history=['current_work']`, matching
   the opening question already spoken by `VoiceSession`.

Use one transaction and a row-level `FOR UPDATE` lock for scheduled activation. Return
409 if another active call exists for a different conversation.

- [ ] **Step 6: Implement `POST /voice-sessions/{session_id}/complete`**

Lock the owned active row, fetch the most recent assistant message as the private
summary, and update only `voice_sessions` plus `career_interview_states`:

```sql
UPDATE public.voice_sessions
SET status = 'completed',
    ended_at = NOW(),
    duration_secs = $3,
    completion_reason = $4,
    summary = $5,
    transcript_version = transcript_version + 1,
    updated_at = NOW()
WHERE id = $1::uuid AND candidate_id = $2::uuid AND status = 'active'
```

Do not call `_apply_voice_conversation_to_profile`. Remove that call from the
legacy `/voice/sessions` compatibility route and have it delegate to the same
completion service.

- [ ] **Step 7: Change scheduling semantics and duration**

- Set `SLOT_MINUTES = 15`.
- Change `get_available_slots` to call `generate_slots` without querying other
  candidates' bookings; the endpoint is a convenience list of future reminder
  times, not inventory.
- Remove the cross-candidate `clash` query from `book_session`.
- Keep duplicate protection per candidate by rejecting another scheduled
  `career_chat` within the same minute.
- Calendar descriptions and notification copy must say “15-minute in-app call.”
- Calendar CTA returns to
  `/dashboard?voice=deep&scheduled_session_id={session_id}`; a Meet link is not
  required. Remove `conferenceData` and `conferenceDataVersion` from
  `GoogleCalendarService.create_event`; return the event ID with a null Meet URL.
  Update the booking response copy so it never tells the candidate to join Meet.

- [ ] **Step 8: Run focused tests and Ruff**

```bash
cd api && uv run pytest tests/test_voice_booking.py tests/test_voice_session_lifecycle.py tests/test_voice_profile_enrichment.py -v
cd api && uv run ruff check src/hireloop_api/routes/voice_sessions.py src/hireloop_api/routes/voice.py src/hireloop_api/services/google_calendar.py
```

Expected: PASS. The profile-enrichment test must now assert no candidate update
occurs from call completion.

- [ ] **Step 9: Commit lifecycle changes**

```bash
git add api/src/hireloop_api/routes/voice_sessions.py api/src/hireloop_api/routes/voice.py api/src/hireloop_api/services/google_calendar.py api/tests/test_voice_booking.py api/tests/test_voice_session_lifecycle.py api/tests/test_voice_profile_enrichment.py
git commit -m "feat: unify Aarya career call lifecycle"
```

### Task 4: Connect Interview Coverage to the Aarya Master Loop

**Files:**
- Modify: `api/src/hireloop_api/services/career_interview.py`
- Modify: `api/src/hireloop_api/routes/chat.py`
- Modify: `api/src/hireloop_api/agents/aarya/agent.py`
- Create: `api/tests/test_aarya_voice_interview_mode.py`

- [ ] **Step 1: Write failing prompt and mutation-guard tests**

```python
def test_career_interview_prompt_asks_selected_focus() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="I build APIs")],
        voice_mode=True,
        memory="",
        open_questions=[],
        career_interview_focus="impact",
        career_interview_should_wrap=False,
    )
    assert "career_interview_focus: impact" in prompt
    assert "Do not update the candidate profile" in prompt


def test_career_interview_blocks_profile_mutation_tool() -> None:
    result = blocked_career_interview_mutation(
        tool_name="update_profile", career_interview_mode=True
    )
    assert result == {
        "error": "Profile changes from this private call require candidate review."
    }
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
cd api && uv run pytest tests/test_aarya_voice_interview_mode.py -v
```

Expected: FAIL because interview context fields and guard do not exist.

- [ ] **Step 3: Add DB repository functions to `career_interview.py`**

Implement:

```python
async def load_active_interview(
    db: asyncpg.Connection,
    *,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> ActiveCareerInterview | None:
    row = await db.fetchrow(
        """
        SELECT vs.id, vs.candidate_id, vs.conversation_id, vs.started_at, cis.state
        FROM public.voice_sessions vs
        JOIN public.career_interview_states cis ON cis.session_id = vs.id
        WHERE vs.id = $1 AND vs.candidate_id = $2
          AND vs.session_type = 'career_chat' AND vs.status = 'active'
        """,
        session_id,
        candidate_id,
    )
    if row is None or row["conversation_id"] is None or row["started_at"] is None:
        return None
    raw_state = row["state"]
    coverage = (
        CareerInterviewCoverage.model_validate_json(raw_state)
        if isinstance(raw_state, str)
        else CareerInterviewCoverage.model_validate(raw_state)
    )
    return ActiveCareerInterview(
        session_id=row["id"],
        candidate_id=row["candidate_id"],
        conversation_id=row["conversation_id"],
        started_at=row["started_at"],
        coverage=coverage,
    )


async def record_turn_and_select_focus(
    db: asyncpg.Connection,
    *,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    candidate_text: str,
) -> NextInterviewFocus:
    async with db.transaction():
        row = await db.fetchrow(
            """
            SELECT cis.state, vs.started_at
            FROM public.career_interview_states cis
            JOIN public.voice_sessions vs ON vs.id = cis.session_id
            WHERE cis.session_id = $1 AND cis.candidate_id = $2
              AND vs.status = 'active'
            FOR UPDATE OF cis
            """,
            session_id,
            candidate_id,
        )
        if row is None or row["started_at"] is None:
            raise LookupError("Active career interview not found")
        raw_state = row["state"]
        state = (
            CareerInterviewCoverage.model_validate_json(raw_state)
            if isinstance(raw_state, str)
            else CareerInterviewCoverage.model_validate(raw_state)
        )
        state = record_candidate_answer(state, candidate_text)
        elapsed = max(0, int((datetime.now(UTC) - row["started_at"]).total_seconds()))
        focus = select_next_focus(state, elapsed_seconds=elapsed)
        state.current_focus = focus.topic
        if focus.topic is not None:
            state.question_history.append(focus.topic)
        await db.execute(
            """
            UPDATE public.career_interview_states
            SET state = $3::jsonb, state_version = state_version + 1, updated_at = NOW()
            WHERE session_id = $1 AND candidate_id = $2
            """,
            session_id,
            candidate_id,
            state.model_dump_json(),
        )
        return focus
```

Add `import uuid`, `from datetime import UTC, datetime`, and `import asyncpg`.

- [ ] **Step 4: Extend the chat request and Aarya state**

Add to `SendMessageRequest`:

```python
voice_session_id: uuid.UUID | None = None
```

Add to `AaryaState`:

```python
career_interview_mode: bool
career_interview_focus: str | None
career_interview_prompt_hint: str | None
career_interview_should_wrap: bool
```

When `content_type == "voice"` and `voice_session_id` is supplied, verify the
active session belongs to the conversation and candidate, then call
`record_turn_and_select_focus`. Reject an invalid/non-active session with 409.
Ordinary voice chat without a career-call session remains backward compatible.

- [ ] **Step 5: Inject strict interview guidance**

Extend `build_turn_context_prompt` with optional interview fields and append:

```python
if career_interview_focus:
    guidance.extend(
        [
            f"- career_interview_focus: {career_interview_focus}",
            f"- focus_guidance: {career_interview_prompt_hint}",
            "- Ask one natural question for this focus after briefly acknowledging the answer.",
            "- Do not update the candidate profile or job preferences from this private call.",
            "- Do not infer age, gender, religion, caste, disability, family status, accent, emotion, or personality.",
        ]
    )
if career_interview_should_wrap:
    guidance.append(
        "- Wrap up now: briefly recap what you understood, mention uncertainty, and close warmly."
    )
```

- [ ] **Step 6: Add a hard tool guard**

Add this pure helper next to the routing helpers so the hard policy is directly
testable:

```python
def blocked_career_interview_mutation(
    *, tool_name: str, career_interview_mode: bool
) -> dict[str, str] | None:
    if career_interview_mode and tool_name in {"update_profile", "update_job_preferences"}:
        return {"error": "Profile changes from this private call require candidate review."}
    return None
```

At the beginning of the existing `_execute_one` `try` block, assign `blocked`
from this helper. If non-null, use it as `result` and skip the existing
`profile_read`/`job_search`/mutation `if` chain; otherwise enter that unchanged
chain. Set `local_actions` only for an executed tool, not for a blocked mutation.
Keep this guard even though the prompt tells Aarya not to mutate.

- [ ] **Step 7: Run focused chat/agent tests**

```bash
cd api && uv run pytest tests/test_career_interview_policy.py tests/test_aarya_voice_interview_mode.py tests/test_aarya_model_routing.py tests/test_chat_streaming.py -v
```

Expected: PASS with no new warnings.

- [ ] **Step 8: Commit Aarya integration**

```bash
git add api/src/hireloop_api/services/career_interview.py api/src/hireloop_api/routes/chat.py api/src/hireloop_api/agents/aarya/agent.py api/tests/test_aarya_voice_interview_mode.py
git commit -m "feat: guide Aarya with private interview coverage"
```

### Task 5: Add a Zod-Validated Voice Session Client

**Files:**
- Create: `app/src/lib/api/voiceSessions.ts`
- Modify: `app/src/lib/chat/aaryaStream.ts`

- [ ] **Step 1: Create strict response schemas and client functions**

```typescript
import { z } from "zod";
import { apiAuthFetch } from "@/lib/api/auth-fetch";

const careerCallSchema = z.object({
  id: z.string().uuid(),
  conversation_id: z.string().uuid().nullable().optional(),
  status: z.enum(["scheduled", "active", "completed", "cancelled"]),
  scheduled_at: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
});

export type CareerCall = z.infer<typeof careerCallSchema>;

async function parseOrThrow<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  const body: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = z.object({ detail: z.string().optional() }).safeParse(body);
    throw new Error(detail.success && detail.data.detail
      ? detail.data.detail
      : `Voice session request failed (${response.status})`);
  }
  return schema.parse(body);
}

export async function startCareerCall(input: {
  conversationId: string;
  scheduledSessionId?: string;
  consent: boolean;
}): Promise<CareerCall> {
  const response = await apiAuthFetch("/api/v1/voice-sessions/start", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: input.conversationId,
      scheduled_session_id: input.scheduledSessionId,
      consent: input.consent,
      consent_version: "career-call-v1",
    }),
  });
  return parseOrThrow(response, careerCallSchema);
}

export async function completeCareerCall(
  sessionId: string,
  input: {
    durationSeconds: number;
    completionReason: "candidate_ended" | "time_limit" | "coverage_complete" | "interrupted";
  },
): Promise<CareerCall> {
  const response = await apiAuthFetch(`/api/v1/voice-sessions/${sessionId}/complete`, {
    method: "POST",
    body: JSON.stringify({
      duration_seconds: input.durationSeconds,
      completion_reason: input.completionReason,
    }),
  });
  return parseOrThrow(response, careerCallSchema);
}
```

Add `scheduleCareerCall`, `listCareerCalls`, and `cancelCareerCall` using the same
schema. `scheduleCareerCall(isoTime)` posts `{ start_time: isoTime,
session_type: "career_chat" }` to `/api/v1/voice-sessions/book` and maps its
`session_id` and `start_time` into `CareerCall`. `listCareerCalls()` parses an
array of `careerCallSchema`. `cancelCareerCall(sessionId)` calls the existing
DELETE endpoint and requires an OK response. Scheduling accepts an ISO time
directly; it does not fetch or reserve global availability.

- [ ] **Step 2: Pass the session ID through the SSE client**

Change the context type and request body:

```typescript
context?: { jobId?: string; voiceSessionId?: string }
```

```typescript
body: JSON.stringify({
  content,
  content_type: contentType,
  job_id: context?.jobId,
  voice_session_id: context?.voiceSessionId,
}),
```

- [ ] **Step 3: Run TypeScript verification**

```bash
pnpm --filter app typecheck
pnpm --filter app lint
```

Expected: both commands exit zero.

- [ ] **Step 4: Commit the client contract**

```bash
git add app/src/lib/api/voiceSessions.ts app/src/lib/chat/aaryaStream.ts
git commit -m "feat: add career call API client"
```

### Task 6: Build Consent, Start-Now, and Schedule-Later UX

**Files:**
- Modify: `app/src/components/dashboard/HomePanel.tsx`
- Modify: `app/src/components/chat/VoiceDeepDiveModal.tsx`
- Create: `app/src/components/chat/ScheduleCareerCall.tsx`
- Modify: `app/src/app/dashboard/DashboardClient.tsx`

- [ ] **Step 1: Add two explicit dashboard actions**

Replace the single link with `Start now` and `Schedule for later`. `Start now`
continues to open `?voice=deep`; `Schedule for later` opens a small scheduling
panel. Copy must say the call is private and no audio is saved.

```tsx
<div className="flex flex-wrap gap-2">
  <Link href="/dashboard?voice=deep&panel=jobs" className={cn(BTN_PRIMARY, "h-10 px-4")}>
    Start now
  </Link>
  <Button variant="secondary" onClick={() => setScheduling(true)}>
    Schedule for later
  </Button>
</div>
<p className="text-micro text-ink-500">
  Your transcript stays private. Audio is not saved.
</p>
```

- [ ] **Step 2: Create the scheduler component**

Use a `datetime-local` field, convert it to ISO, require a future time, and call
`scheduleCareerCall`. The success state displays the local date/time and an
in-app start link. Do not display scarcity, available slots, or a Meet link.

```tsx
const scheduledAt = new Date(localValue);
if (Number.isNaN(scheduledAt.valueOf()) || scheduledAt <= new Date()) {
  setError("Choose a future date and time.");
  return;
}
const session = await scheduleCareerCall(scheduledAt.toISOString());
setBooked(session);
```

- [ ] **Step 3: Add the consent gate to the modal**

Before rendering `VoiceSession`, show:

- Purpose: improve candidate-owned profile and job recommendations.
- Transcript: private to the candidate and Hireschema processing.
- Audio: not stored.
- Recruiter sharing: not included; later sharing requires separate consent.
- A required checkbox and `Continue` button.

Consent must be sent to the backend start route; do not store it only in browser
state.

- [ ] **Step 4: Support scheduled deep links**

Read `scheduled_session_id` from dashboard search params and pass it through
`DashboardClient` to `VoiceDeepDiveModal`, then to `VoiceSession`. Closing the
modal without starting leaves the scheduled row intact.

- [ ] **Step 5: Run frontend checks**

```bash
pnpm --filter app typecheck
pnpm --filter app lint
pnpm --filter app build
```

Expected: all exit zero.

- [ ] **Step 6: Commit entry UX**

```bash
git add app/src/components/dashboard/HomePanel.tsx app/src/components/chat/VoiceDeepDiveModal.tsx app/src/components/chat/ScheduleCareerCall.tsx app/src/app/dashboard/DashboardClient.tsx
git commit -m "feat: add private career call scheduling"
```

### Task 7: Make the Live Voice Component Session-Aware and Time-Bounded

**Files:**
- Modify: `app/src/app/voice/VoiceSession.tsx`
- Modify: `app/src/components/chat/VoiceDeepDiveModal.tsx`

- [ ] **Step 1: Separate conversation ID from voice-session ID**

Replace the ambiguous `sessionIdRef` with:

```typescript
const conversationIdRef = useRef<string | null>(null);
const voiceSessionIdRef = useRef<string | null>(null);
```

The start sequence must:

1. Resolve the existing Aarya conversation.
2. Call `startCareerCall` with consent and optional scheduled session ID.
3. Store both IDs.
4. Start greeting/timer only after backend start succeeds.

- [ ] **Step 2: Attach the voice-session ID to every turn**

```typescript
await streamAaryaMessage(
  conversationId,
  userText,
  "voice",
  callbacks,
  ctrl.signal,
  { voiceSessionId: voiceSessionIdRef.current ?? undefined },
);
```

- [ ] **Step 3: Enforce the 15-minute lifecycle**

Use constants rather than embedded numbers:

```typescript
const CALL_SECONDS = 15 * 60;
const WRAP_WARNING_SECONDS = 14 * 60;
```

At 14 minutes, show “Aarya is wrapping up.” The backend focus policy will cause
the next reply to recap. At 15 minutes, stop the mic and complete with
`completionReason: "time_limit"`. Cap the backend duration at 16 minutes for
network/cleanup tolerance.

- [ ] **Step 4: Complete the same server row**

Replace the old best-effort `POST /voice/sessions` call:

```typescript
if (voiceSessionIdRef.current) {
  await completeCareerCall(voiceSessionIdRef.current, {
    durationSeconds: duration,
    completionReason,
  });
}
```

If completion fails, keep the modal open with a Retry saving button. Do not hide
the error or redirect while the server still thinks the session is active.

- [ ] **Step 5: Preserve interruption behavior**

On component unmount during an active call, stop local media but do not mark the
session completed. Reopening the same scheduled/active deep link calls `start`
idempotently and resumes the row. The existing conversation messages preserve
prior turns.

- [ ] **Step 6: Run frontend checks and manual local smoke**

```bash
pnpm --filter app typecheck
pnpm --filter app lint
pnpm --filter app build
```

Manual smoke with API and app running:

1. Open the dashboard voice modal.
2. Confirm no microphone starts before consent.
3. Start a call and verify one active `voice_sessions` row.
4. Speak two turns and verify messages plus `career_interview_states.state_version` advance.
5. Close/reopen and verify the same active row resumes.
6. End and verify that row becomes completed and no candidate field changes.

- [ ] **Step 7: Commit live-call changes**

```bash
git add app/src/app/voice/VoiceSession.tsx app/src/components/chat/VoiceDeepDiveModal.tsx
git commit -m "feat: make Aarya career calls durable and time bounded"
```

### Task 8: Correct Reminder Links and User-Facing Documentation

**Files:**
- Modify: `api/src/hireloop_api/services/notifications.py`
- Modify: `app/src/app/terms/page.tsx`
- Modify: `PHASE_TRACKER.md`
- Test: `api/tests/test_notifications.py`

- [ ] **Step 1: Write a failing reminder-link test**

```python
@pytest.mark.asyncio
async def test_career_call_reminder_links_to_scheduled_session(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_send_category_email(*args: object, **kwargs: object) -> dict[str, bool]:
        captured.update(kwargs["template_data"])
        return {"sent": True}

    monkeypatch.setattr(notifications, "send_category_email", fake_send_category_email)
    monkeypatch.setattr(notifications, "_already_notified", AsyncMock(return_value=False))
    monkeypatch.setattr(notifications, "_log_in_app", AsyncMock(return_value=None))
    db = AsyncMock()
    db.fetchrow.return_value = {
        "status": "scheduled",
        "email": "candidate@example.com",
        "full_name": "Candidate",
    }
    await notifications.send_interview_reminder_email(
        db,
        Settings(_env_file=None, environment="test", public_app_url="https://app.test"),
        user_id="22222222-2222-2222-2222-222222222222",
        session_id="11111111-1111-1111-1111-111111111111",
        session_type="career_chat",
        scheduled_at=datetime(2026, 7, 23, 5, 0, tzinfo=UTC),
    )
    assert str(captured["cta_url"]).endswith(
        "/dashboard?voice=deep&scheduled_session_id=11111111-1111-1111-1111-111111111111"
    )
```

Create `api/tests/test_notifications.py` with imports for `UTC`, `datetime`,
`AsyncMock`, `pytest`, `Settings`, and the notifications module.

- [ ] **Step 2: Run the test and verify RED**

```bash
cd api && uv run pytest tests/test_notifications.py::test_career_call_reminder_links_to_scheduled_session -v
```

Expected: FAIL because the current CTA is only `/dashboard`.

- [ ] **Step 3: Implement the deep link and truthful copy**

For `session_type == "career_chat"`, set the CTA to the scheduled-session deep
link and label it “Start your private 15-minute call.” Keep mock-interview copy
unchanged. Update Terms text so Google Calendar is described as optional reminder
enrichment; it must not promise Google Meet.

- [ ] **Step 4: Update the phase tracker**

Record S05 as:

- 15-minute private career-discovery session.
- Start now or schedule without exclusive capacity.
- No audio storage by default.
- Transcript persists privately.
- Profile mutation is deferred to candidate-confirmed Phase 2 review.

- [ ] **Step 5: Run focused verification and commit**

```bash
cd api && uv run pytest tests/test_notifications.py -v
pnpm --filter app typecheck
pnpm --filter app lint
git add api/src/hireloop_api/services/notifications.py api/tests/test_notifications.py app/src/app/terms/page.tsx PHASE_TRACKER.md
git commit -m "docs: align career call reminders and privacy copy"
```

### Task 9: Full Phase 1 Verification

**Files:**
- No new files unless verification exposes a regression.

- [ ] **Step 1: Run focused backend tests**

```bash
cd api && uv run pytest \
  tests/test_career_interview_policy.py \
  tests/test_voice_session_lifecycle.py \
  tests/test_voice_booking.py \
  tests/test_voice_profile_enrichment.py \
  tests/test_aarya_voice_interview_mode.py \
  tests/test_voice_speech_sanitization.py \
  tests/test_voice_keyterms.py \
  tests/test_notifications.py -v
```

Expected: all PASS.

- [ ] **Step 2: Run backend quality gates**

```bash
cd api && uv run ruff check .
cd api && uv run ruff format --check .
```

Expected: both exit zero.

- [ ] **Step 3: Run frontend quality gates**

```bash
pnpm --filter app typecheck
pnpm --filter app lint
pnpm --filter app build
```

Expected: all exit zero.

- [ ] **Step 4: Run migration and RLS smoke against local Supabase**

```bash
supabase db reset
cd api && uv run pytest tests/integration -v
```

Expected: migration succeeds and integration tests pass. Do not run
`supabase db push` against production as part of automated verification.

- [ ] **Step 5: Run real-provider beta smoke in staging**

Verify:

1. Deepgram live STT and TTS with the timeout fallback.
2. English and Hinglish turns.
3. Two candidates schedule the same minute successfully.
4. An interrupted active call resumes the same row.
5. The 14-minute wrap guidance and 15-minute completion.
6. No `recording_url` and no voice-derived candidate field updates.
7. Consent-log entry and candidate-only RLS access.
8. Reminder deep link activates the correct scheduled session.

- [ ] **Step 6: Review the final diff for scope and secrets**

```bash
git status --short
git diff --check
git diff --stat
```

Confirm only Phase 1 files changed, no `.env` or credential files are staged,
and unrelated user work remains untouched.

- [ ] **Step 7: Commit any verification-only corrections**

If verification required changes, commit only those files:

```bash
git add \
  supabase/migrations/20260721150000_aarya_career_call_phase1.sql \
  api/src/hireloop_api/models/career_interview.py \
  api/src/hireloop_api/services/career_interview.py \
  api/src/hireloop_api/routes/voice_sessions.py \
  api/src/hireloop_api/routes/voice.py \
  api/src/hireloop_api/routes/chat.py \
  api/src/hireloop_api/agents/aarya/agent.py \
  api/src/hireloop_api/services/google_calendar.py \
  api/src/hireloop_api/services/notifications.py \
  api/tests/test_career_interview_policy.py \
  api/tests/test_voice_session_lifecycle.py \
  api/tests/test_voice_booking.py \
  api/tests/test_voice_profile_enrichment.py \
  api/tests/test_aarya_voice_interview_mode.py \
  api/tests/test_notifications.py \
  app/src/lib/api/voiceSessions.ts \
  app/src/lib/chat/aaryaStream.ts \
  app/src/app/voice/VoiceSession.tsx \
  app/src/components/chat/VoiceDeepDiveModal.tsx \
  app/src/components/chat/ScheduleCareerCall.tsx \
  app/src/components/dashboard/HomePanel.tsx \
  app/src/app/dashboard/DashboardClient.tsx \
  app/src/app/terms/page.tsx \
  PHASE_TRACKER.md
git commit -m "test: verify trustworthy Aarya career calls"
```

If no corrections were required, do not create an empty commit.
