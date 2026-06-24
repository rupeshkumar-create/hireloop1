# Aarya Text And Voice Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Aarya’s text and voice experience smoother, faster-feeling, and more advanced while preserving the existing MVP architecture.

**Architecture:** Keep the current LangGraph agent, chat SSE route, `useVoice` hook, and `/voice` call screen. Add small deterministic helpers for runtime prompt context and stream status, then improve frontend voice state handling around live captions, empty transcripts, barge-in, and status display.

**Tech Stack:** FastAPI, Python 3.12, LangGraph, Pydantic v2, Next.js 15, TypeScript, React, Tailwind, Deepgram STT/TTS.

---

## File Structure

- Modify `api/src/hireloop_api/agents/aarya/agent.py` to add deterministic turn guidance and inject it into the system prompt.
- Modify `api/src/hireloop_api/routes/chat.py` to expose clearer status helpers and stream status labels.
- Modify `api/src/hireloop_api/routes/voice.py` only if speech sanitization tests expose gaps.
- Modify `app/src/components/chat/ChatInterface.tsx` to show live captions, improve empty transcript handling, and make voice interaction feel more responsive.
- Modify `app/src/app/voice/VoiceSession.tsx` to show chat stream statuses and no-speech retry hints during the 15-minute call.
- Modify `app/src/lib/hooks/useVoice.ts` only for minimal hook API additions if the UI needs them.
- Add or update `api/tests/test_aarya_agent_context.py`.
- Add or update `api/tests/test_chat_stream_status.py`.
- Add or update `api/tests/test_voice_speech_sanitization.py`.

---

### Task 1: Add Aarya Turn Context

**Files:**
- Modify: `api/src/hireloop_api/agents/aarya/agent.py`
- Test: `api/tests/test_aarya_agent_context.py`

- [ ] **Step 1: Write failing tests**

Create `api/tests/test_aarya_agent_context.py`:

```python
from langchain_core.messages import HumanMessage

from hireloop_api.agents.aarya.agent import build_turn_context_prompt


def test_turn_context_prompt_marks_voice_mode_and_short_replies() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="I lead growth at a SaaS startup")],
        voice_mode=True,
        memory="Candidate wants Head of Growth roles.",
        open_questions=["What CTC range are you targeting?"],
    )

    assert "Current turn context" in prompt
    assert "mode: voice" in prompt
    assert "Keep the next reply short and spoken" in prompt
    assert "Head of Growth" in prompt
    assert "What CTC range are you targeting?" in prompt


def test_turn_context_prompt_detects_job_search_intent() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="Find me remote Head of Growth jobs")],
        voice_mode=False,
        memory="",
        open_questions=[],
    )

    assert "likely_intent: job_search" in prompt
    assert "build_career_path before job_search" in prompt
    assert "remote" in prompt.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd api && pytest tests/test_aarya_agent_context.py -q`

Expected: failure because `build_turn_context_prompt` does not exist.

- [ ] **Step 3: Implement context helper**

In `api/src/hireloop_api/agents/aarya/agent.py`, add a pure helper near the prompt constants:

```python
def _last_human_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def _detect_likely_intent(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("job", "role", "opening", "match", "remote", "onsite")):
        return "job_search"
    if any(token in lowered for token in ("resume", "cv", "linkedin", "profile")):
        return "profile_improvement"
    if any(token in lowered for token in ("intro", "hiring manager", "refer", "connect")):
        return "intro_request"
    if any(token in lowered for token in ("salary", "ctc", "lpa", "notice")):
        return "preference_update"
    return "general_career_chat"


def build_turn_context_prompt(
    *,
    messages: list[BaseMessage],
    voice_mode: bool,
    memory: str,
    open_questions: list[str],
) -> str:
    last_text = _last_human_text(messages).strip()
    likely_intent = _detect_likely_intent(last_text)
    guidance: list[str] = [
        "Current turn context:",
        f"- mode: {'voice' if voice_mode else 'text'}",
        f"- likely_intent: {likely_intent}",
    ]
    if likely_intent == "job_search":
        guidance.append("- action_policy: build_career_path before job_search; search India roles only.")
    elif likely_intent == "intro_request":
        guidance.append("- action_policy: require explicit candidate approval before request_intro.")
    elif likely_intent == "profile_improvement":
        guidance.append("- action_policy: use known resume, LinkedIn, memory, and profile facts before asking.")
    elif likely_intent == "preference_update":
        guidance.append("- action_policy: update saved preferences when the candidate states a clear filter.")
    else:
        guidance.append("- action_policy: answer directly, then ask at most one useful follow-up.")

    if voice_mode:
        guidance.append("- delivery: Keep the next reply short and spoken; no markdown, emoji, bullets, or headings.")
    else:
        guidance.append("- delivery: Keep the next reply compact and mobile-friendly with one clear next action.")

    trimmed_memory = memory.strip()
    if trimmed_memory:
        guidance.append(f"- memory_hint: {trimmed_memory[:500]}")

    clean_questions = [q.strip() for q in open_questions if q.strip()]
    if clean_questions:
        guidance.append("- best_profile_gap_to_ask_if_natural: " + clean_questions[0])

    return "\n".join(guidance)
```

Then append this helper output inside `agent_node` before creating the `SystemMessage`.

- [ ] **Step 4: Run focused tests**

Run: `cd api && pytest tests/test_aarya_agent_context.py -q`

Expected: tests pass.

---

### Task 2: Improve Stream Status Labels

**Files:**
- Modify: `api/src/hireloop_api/routes/chat.py`
- Test: `api/tests/test_chat_stream_status.py`

- [ ] **Step 1: Write failing tests**

Create `api/tests/test_chat_stream_status.py`:

```python
from hireloop_api.routes.chat import tool_status_label


def test_tool_status_label_is_specific_for_job_search() -> None:
    assert tool_status_label("job_search", voice_mode=False) == "Searching India roles…"


def test_tool_status_label_is_spoken_for_voice() -> None:
    assert tool_status_label("job_search", voice_mode=True) == "I’m searching India roles now…"


def test_tool_status_label_handles_unknown_tool() -> None:
    assert tool_status_label("unknown_tool", voice_mode=False) == "Working on your request…"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd api && pytest tests/test_chat_stream_status.py -q`

Expected: failure because `tool_status_label` does not exist.

- [ ] **Step 3: Implement status helper**

In `api/src/hireloop_api/routes/chat.py`, replace direct dictionary access with:

```python
_TEXT_TOOL_STATUS_LABELS: dict[str, str] = {
    "profile_read": "Reading your profile…",
    "build_career_path": "Mapping your career path…",
    "job_search": "Searching India roles…",
    "get_match_score": "Scoring this role…",
    "match_score": "Scoring this role…",
    "save_job": "Saving this role…",
    "request_intro": "Preparing your intro…",
    "direct_apply": "Logging your application…",
    "update_job_preferences": "Updating your filters…",
    "update_profile": "Updating your profile…",
}

_VOICE_TOOL_STATUS_LABELS: dict[str, str] = {
    "profile_read": "I’m checking your profile…",
    "build_career_path": "I’m mapping the best next steps…",
    "job_search": "I’m searching India roles now…",
    "get_match_score": "I’m checking the fit for this role…",
    "match_score": "I’m checking the fit for this role…",
    "save_job": "I’m saving that role…",
    "request_intro": "I’m preparing the intro request…",
    "direct_apply": "I’m logging that application…",
    "update_job_preferences": "I’m updating your filters…",
    "update_profile": "I’m updating your profile…",
}


def tool_status_label(tool_name: str, *, voice_mode: bool = False) -> str:
    labels = _VOICE_TOOL_STATUS_LABELS if voice_mode else _TEXT_TOOL_STATUS_LABELS
    return labels.get(tool_name, "Working on your request…")
```

Update `_tool_status_from_message` to accept `voice_mode: bool` and call `tool_status_label(name, voice_mode=voice_mode)`.

- [ ] **Step 4: Use voice-aware labels in stream**

Pass `body.content_type == "voice"` when calling `_tool_status_from_message`. Change the generic tools update status to `tool_status_label("", voice_mode=body.content_type == "voice")`.

- [ ] **Step 5: Run focused tests**

Run: `cd api && pytest tests/test_chat_stream_status.py -q`

Expected: tests pass.

---

### Task 3: Strengthen Speech Sanitization Tests

**Files:**
- Modify: `api/src/hireloop_api/routes/voice.py`
- Test: `api/tests/test_voice_speech_sanitization.py`

- [ ] **Step 1: Write or update tests**

Create `api/tests/test_voice_speech_sanitization.py`:

```python
from hireloop_api.routes.voice import _sanitize_for_speech


def test_sanitize_for_speech_removes_markdown_and_emoji() -> None:
    text = "**Great fit** 🎯\n- Apply at [Razorpay](https://example.com)"

    spoken = _sanitize_for_speech(text)

    assert spoken == "Great fit. Apply at Razorpay"


def test_sanitize_for_speech_keeps_lpa_readable() -> None:
    text = "This role is around 30-40 LPA, hybrid in Bengaluru."

    spoken = _sanitize_for_speech(text)

    assert spoken == "This role is around 30-40 LPA, hybrid in Bengaluru."
```

- [ ] **Step 2: Run tests**

Run: `cd api && pytest tests/test_voice_speech_sanitization.py -q`

Expected: pass if current sanitizer is sufficient, otherwise fail on punctuation cleanup.

- [ ] **Step 3: Patch sanitizer only if needed**

If the first test fails because of spacing around punctuation, add:

```python
out = re.sub(r"\s+([.,!?])", r"\1", out)
```

before `return out.strip()`.

- [ ] **Step 4: Run focused tests**

Run: `cd api && pytest tests/test_voice_speech_sanitization.py -q`

Expected: tests pass.

---

### Task 4: Smooth Inline Chat Voice UX

**Files:**
- Modify: `app/src/components/chat/ChatInterface.tsx`
- Test: TypeScript validation

- [ ] **Step 1: Extend hook destructuring**

In `ChatInterface`, destructure `interimTranscript` and `audioLevel` from `useVoice()`.

- [ ] **Step 2: Improve empty transcript behavior**

In `handleMicToggle`, when `stopRecording()` returns an empty string, append a system note:

```ts
appendSystemNote("I didn’t catch that. Tap the mic and try again, or type it instead.");
```

Do not set `pendingVoiceTranscript` for an empty transcript.

- [ ] **Step 3: Show live captions**

Above `VoiceTranscriptReview`, render a small live caption panel when `isRecording && interimTranscript`:

```tsx
{isRecording && interimTranscript && (
  <div className="rounded-xl border border-ink-200 bg-paper-1 px-3 py-2">
    <p className="text-micro uppercase tracking-wide text-ink-400">Listening</p>
    <p className="text-small text-ink-800">{interimTranscript}</p>
  </div>
)}
```

- [ ] **Step 4: Add subtle mic level feedback**

Use `audioLevel` to add a small inline meter under the “Listening…” state. Keep it decorative and `aria-hidden`.

- [ ] **Step 5: Ensure barge-in remains natural**

Keep `stopSpeaking()` before `startRecording()` and do not disable the mic when `isPlaying`; instead let mic click stop playback and start recording.

- [ ] **Step 6: Run app typecheck**

Run: `./node_modules/.bin/tsc --noEmit`

Expected: no TypeScript errors.

---

### Task 5: Smooth 15-Minute Voice Session UX

**Files:**
- Modify: `app/src/app/voice/VoiceSession.tsx`
- Test: TypeScript validation

- [ ] **Step 1: Track stream status**

Add `const [streamStatus, setStreamStatus] = useState<string | null>(null);`.

- [ ] **Step 2: Parse status events**

In `streamAaryaReply`, parse `status?: string` from SSE payloads and call `setStreamStatus(parsed.status)` when present.

- [ ] **Step 3: Clear status on text**

When a text chunk arrives, clear status with `setStreamStatus(null)`.

- [ ] **Step 4: Retry no-speech turns**

In `listenForUser`, if `userTranscript.trim()` is empty, set:

```ts
setErrorMsg("I didn’t catch that — try once more, or tap end call if you’re done.");
```

Then return to `user_listening` instead of failing the call.

- [ ] **Step 5: Show status label**

Render `streamStatus ?? statusLabel[turnState]` in the status paragraph.

- [ ] **Step 6: Run app typecheck**

Run: `./node_modules/.bin/tsc --noEmit`

Expected: no TypeScript errors.

---

### Task 6: Full Verification

**Files:**
- No code changes.

- [ ] **Step 1: Run focused API tests**

Run: `cd api && pytest tests/test_aarya_agent_context.py tests/test_chat_stream_status.py tests/test_voice_speech_sanitization.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run API suite**

Run: `cd api && pytest tests -q`

Expected: all tests pass.

- [ ] **Step 3: Run frontend typecheck**

Run: `./node_modules/.bin/tsc --noEmit`

Expected: no TypeScript errors.

- [ ] **Step 4: Run frontend lint**

Run: `./node_modules/.bin/next lint`

Expected: existing warnings may remain, no new errors.

- [ ] **Step 5: Run frontend build**

Run: `npm run build`

Expected: build passes. If Google Fonts/network blocks the build in sandbox, rerun with escalation.

---

## Self-Review

- Spec coverage: agent context, status smoothness, chat voice captions, empty transcript handling, voice call statuses, and verification are all mapped to tasks.
- Placeholder scan: no task relies on vague “do it later” language; each task names files and expected behavior.
- Type consistency: backend helper names are `build_turn_context_prompt` and `tool_status_label`; frontend additions use existing `useVoice` state names `interimTranscript` and `audioLevel`.
- Constraint check: no new provider, no direct frontend DB writes, no LinkedIn scraping changes, no removal of `/voice`.
