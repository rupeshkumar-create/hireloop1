# Chat + Voice Interface Upgrade Design

**Date:** 2026-07-24  
**Status:** Approved design  
**Product:** Hireschema candidate SPA (`app/`) + FastAPI voice/chat

## Problem

Candidate chat already shares one SSE pipeline for text and voice, but the surface feels unfinished versus Claude/Codex-style chat and MVP rule R8:

- Mic is hold-to-talk only; no latch/toggle.
- `audioLevel` is computed but unused in the composer (no waveform).
- Streaming blocks send/mic; no real barge-in.
- Auto-send vs review-before-send prefs exist in localStorage with no UI.
- 15‑min career call lives in a separate modal/`/voice` screen, so voice feels like two products.
- Deepgram TTS timeouts exceed R16’s 10s guard; live STT still uses deprecated `ScriptProcessorNode`.
- `ChatInterface.tsx` (~2.8k lines) blocks safe iteration.

## Goals

1. Composer waveform + **toggle-only** mic.
2. **Full barge-in**: new send or mic while streaming aborts current SSE + TTS and starts that turn.
3. Settings UI for **auto-send vs review** (default auto-send).
4. **Fold career call into the chat thread** (banner + timer; no primary separate voice screen).
5. TTS **10s** guard (client + API) + **AudioWorklet** for live PCM.
6. Split `ChatInterface` into focused modules so the above is maintainable.

## Non-goals

- No new voice provider; keep Deepgram + browser fallbacks.
- No message queue (explicitly rejected; barge-in replaces queue).
- No hold-to-talk dual mode (toggle-only chosen).
- No rewriting LangGraph / Aarya tools.
- No Zustand migration required for this pass (local React state + existing prefs OK).
- No payment, recruiter Nitya chat, or public-profile chat voice.

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Career call placement | **B** — fold into same chat thread |
| Mid-stream interrupt | **C** — full barge-in |
| Mic interaction | **B** — toggle only |
| Voice send default | **C** — auto-send default + settings toggle for review |
| Implementation style | **1** — incremental extract + features in place |

## Architecture

```
ChatInterface (orchestrator)
├── messages rendering (existing cards / timeline / markdown)
├── useChatStream          — SSE, AbortController, barge-in
├── ChatComposer           — textarea, send, mic, call start, settings, waveform
├── InThreadCallBanner     — timer, mute, end, levels (career-call mode)
└── useVoice               — STT/TTS (AudioWorklet + 10s TTS)

Same primary chat session + same POST .../messages SSE.
Career-call mode attaches voice_session_id metadata; unlock/complete APIs unchanged.
```

### File responsibilities (target)

| Unit | Responsibility |
|------|----------------|
| `ChatInterface.tsx` | Wire session, history, messages, kickoff; compose children |
| `ChatComposer.tsx` | Input bar UI + mic toggle + settings menu + call CTA |
| `ComposerWaveform.tsx` | Render bars from `audioLevel` (listening + speaking) |
| `useChatStream.ts` | `sendMessage`, abort active stream, barge-in entry |
| `InThreadCallBanner.tsx` | Career-call chrome over the thread |
| `voicePreferences.ts` | Existing prefs + any new keys (already present) |
| `useVoice.ts` | AudioWorklet path; TTS fetch/play abort at 10s |
| `api/.../deepgram_tts.py` | httpx timeout **10.0** |

`VoiceDeepDiveModal` / dedicated `/voice` page: stop being the primary entry. Prefer redirect or thin wrapper that opens dashboard chat in career-call mode. Keep APIs (`voice-sessions` start/complete) intact.

## Feature design

### Composer + mic

- Mic button: tap to start recording; tap again (or Stop square) to finish.
- While recording: pulse + waveform; interim captions in status strip with `aria-live="polite"`.
- Ignore captures shorter than ~350ms (discard without empty-STT retry loop).
- Settings control (gear or “…” menu on composer):
  - Reply mode: voice / text (existing)
  - After recording: **Send immediately** (default) | **Review before send**
- “Start career call” control in composer activates in-thread call mode.

### Streaming / barge-in

- Maintain `AbortController` per in-flight SSE (and cancel TTS via existing `interruptSpeech` / generation token).
- If user sends text or starts mic while `isStreaming`:
  1. Abort SSE
  2. Interrupt TTS
  3. Finalize UI state for aborted turn (keep partial assistant text if already shown; mark as interrupted — do not fake completion)
  4. Start the new turn immediately
- Explicit **Stop** control still aborts without starting a new turn.
- Esc: same as Stop when streaming or speaking.

### In-thread career call

- Banner above composer when `callMode === "career"`:
  - Label + countdown (15 min)
  - Waveform / mute / End call
- Continuous listen/speak loop can reuse logic from `VoiceSession`, but UI chrome lives in-thread.
- On End or timer expiry: call existing complete API; banner dismisses; composer returns to normal toggle mic.
- Consent (if currently in `VoiceDeepDiveModal`) moves to a lightweight confirm before entering call mode.

### Correctness / longevity

- Client TTS request + playback guard: **max 10s** (R16 #17). On timeout, fall back to text reply / stop audio without blocking chat.
- Server Deepgram TTS `httpx` timeout: **10.0** seconds.
- Replace `ScriptProcessorNode` with AudioWorklet module for PCM → live STT WebSocket; keep batch + Web Speech fallbacks.
- Update `getVoiceSupportStatus` so Deepgram `<audio>` path counts as TTS-capable.

### Split ChatInterface

Extract in this order to avoid a big-bang rewrite:

1. `ComposerWaveform` + mic toggle wiring (small, visible win)
2. Settings menu for send-on-release / review
3. `useChatStream` + barge-in
4. `ChatComposer` extraction
5. `InThreadCallBanner` + retire modal as primary
6. AudioWorklet + TTS 10s (can parallelize with 3–5)

Each step must leave chat usable.

## Error handling

| Case | Behavior |
|------|----------|
| Mic permission denied | Keep typing; show existing under-composer error |
| Empty STT after valid toggle | One retry max, then system note |
| Too-short toggle | Silent discard + micro hint once |
| TTS timeout / failure | Interrupt audio; keep text on screen |
| Barge-in mid-stream | Abort cleanly; no duplicate assistant bubbles |
| Call complete API fails | Banner ends locally; non-blocking toast; session can reconcile on next start |

## Testing

- Unit (app): prefs helpers; barge-in abort helper; waveform props; min-hold discard.
- Unit (api): TTS client timeout config = 10s.
- Manual: toggle mic + waveform; barge-in with text and mic; review mode path; start/mute/end in-thread call; Esc stop; Safari smoke if available.

## Success criteria

- User can toggle mic and see live waveform in composer.
- Sending or speaking during a stream cancels it and starts the new turn.
- Review-before-send is discoverable and persisted.
- Career call starts from composer and runs in-thread with timer; no need for deep-dive modal as primary path.
- TTS never waits >10s on client or server HTTP to Deepgram.
- Live STT uses AudioWorklet (no ScriptProcessor in the happy path).
- `ChatInterface.tsx` is substantially smaller; new units have clear boundaries.

## Out of scope follow-ups

- Fold remaining `/voice` marketing links fully after analytics confirm in-thread usage.
- Keyboard shortcut sheet beyond Esc.
- Edit/resend last user message (not in this pass).
