# Chat + Voice UX Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Aarya chat so toggle mic + waveform, full barge-in, discoverable voice settings, and an in-thread 15‑min career call all work on one surface, with TTS 10s guards, AudioWorklet STT, and a split `ChatInterface`.

**Architecture:** Keep the existing SSE + LangGraph + Deepgram stack. Extract pure helpers and UI modules first, then wire barge-in via the existing `AbortController` in `ChatInterface`, fold career-call chrome into the thread (reuse `VoiceSession` logic), and harden `useVoice` (AudioWorklet + 10s TTS).

**Tech Stack:** Next.js 15, TypeScript, React, Vitest, Tailwind, FastAPI, httpx, Deepgram, Web Audio AudioWorklet.

**Spec:** `docs/superpowers/specs/2026-07-24-chat-voice-ux-upgrade-design.md`

---

## File Structure

| Path | Role |
|------|------|
| Create `app/src/lib/chat/voiceCapture.ts` | Min-duration discard + recording clock helpers |
| Create `app/src/lib/chat/bargeIn.ts` | Pure abort/finalize helpers for stream barge-in |
| Create `app/src/components/chat/ComposerWaveform.tsx` | Level bars from `audioLevel` |
| Create `app/src/components/chat/ChatComposer.tsx` | Composer UI: textarea, send, mic toggle, settings, call CTA |
| Create `app/src/components/chat/InThreadCallBanner.tsx` | Career-call timer / mute / end / waveform |
| Create `app/src/components/chat/CareerCallConsent.tsx` | Lightweight consent before call mode |
| Create `app/public/worklets/pcm-capture-processor.js` | AudioWorkletProcessor for live PCM |
| Modify `app/src/lib/chat/voicePreferences.ts` | No API change required; settings UI consumes existing helpers |
| Modify `app/src/lib/hooks/useVoice.ts` | Toggle-friendly API surface, AudioWorklet, TTS 10s |
| Modify `app/src/lib/chat/aaryaStream.ts` | Ensure abort mid-read cancels cleanly (if gaps) |
| Modify `app/src/components/chat/ChatInterface.tsx` | Wire extracts, barge-in, call mode; shrink |
| Modify `app/src/components/chat/VoiceDeepDiveModal.tsx` | Deprecate as primary; optional thin consent reuse |
| Modify `app/src/app/voice/page.tsx` | Redirect into dashboard chat with call-mode query |
| Modify `app/src/app/dashboard/DashboardClient.tsx` | Honor `?careerCall=1` / `initialCareerCall` |
| Modify `api/src/hireloop_api/services/voice/deepgram_tts.py` | `timeout=10.0` |
| Test `app/src/lib/chat/voiceCapture.test.ts` | |
| Test `app/src/lib/chat/bargeIn.test.ts` | |
| Test `app/src/components/chat/ComposerWaveform.test.tsx` | |
| Test `api/tests/test_deepgram_tts_timeout.py` | |

---

### Task 1: Min-duration voice capture helpers

**Files:**
- Create: `app/src/lib/chat/voiceCapture.ts`
- Test: `app/src/lib/chat/voiceCapture.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import {
  MIN_VOICE_CAPTURE_MS,
  shouldDiscardVoiceCapture,
} from "@/lib/chat/voiceCapture";

describe("voiceCapture", () => {
  it("exports a ~350ms minimum", () => {
    expect(MIN_VOICE_CAPTURE_MS).toBe(350);
  });

  it("discards captures shorter than the minimum", () => {
    expect(shouldDiscardVoiceCapture(0)).toBe(true);
    expect(shouldDiscardVoiceCapture(200)).toBe(true);
    expect(shouldDiscardVoiceCapture(349)).toBe(true);
  });

  it("keeps captures at or above the minimum", () => {
    expect(shouldDiscardVoiceCapture(350)).toBe(false);
    expect(shouldDiscardVoiceCapture(2000)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && pnpm exec vitest run src/lib/chat/voiceCapture.test.ts`

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
/** Ignore accidental mic taps that are too short to contain speech. */
export const MIN_VOICE_CAPTURE_MS = 350;

export function shouldDiscardVoiceCapture(elapsedMs: number): boolean {
  return elapsedMs < MIN_VOICE_CAPTURE_MS;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && pnpm exec vitest run src/lib/chat/voiceCapture.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/chat/voiceCapture.ts app/src/lib/chat/voiceCapture.test.ts
git commit -m "feat(chat): add min-duration voice capture helper"
```

---

### Task 2: Barge-in abort helpers

**Files:**
- Create: `app/src/lib/chat/bargeIn.ts`
- Test: `app/src/lib/chat/bargeIn.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it, vi } from "vitest";
import { abortActiveTurn, shouldBargeIn } from "@/lib/chat/bargeIn";

describe("bargeIn", () => {
  it("barge-in when streaming or send in flight", () => {
    expect(shouldBargeIn({ isStreaming: true, sendInFlight: false })).toBe(true);
    expect(shouldBargeIn({ isStreaming: false, sendInFlight: true })).toBe(true);
    expect(shouldBargeIn({ isStreaming: false, sendInFlight: false })).toBe(false);
  });

  it("aborts controller, interrupts speech, and clears refs", () => {
    const abort = vi.fn();
    const interruptSpeech = vi.fn();
    const controller = { abort } as unknown as AbortController;
    const result = abortActiveTurn({
      abortRef: { current: controller },
      interruptSpeech,
    });
    expect(abort).toHaveBeenCalledOnce();
    expect(interruptSpeech).toHaveBeenCalledOnce();
    expect(result.aborted).toBe(true);
  });

  it("is a no-op when nothing is active", () => {
    const interruptSpeech = vi.fn();
    const result = abortActiveTurn({
      abortRef: { current: null },
      interruptSpeech,
    });
    expect(interruptSpeech).not.toHaveBeenCalled();
    expect(result.aborted).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && pnpm exec vitest run src/lib/chat/bargeIn.test.ts`

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```ts
export function shouldBargeIn(state: {
  isStreaming: boolean;
  sendInFlight: boolean;
}): boolean {
  return state.isStreaming || state.sendInFlight;
}

export function abortActiveTurn(args: {
  abortRef: { current: AbortController | null };
  interruptSpeech: () => void;
}): { aborted: boolean } {
  const controller = args.abortRef.current;
  if (!controller) return { aborted: false };
  try {
    controller.abort();
  } catch {
    /* ignore */
  }
  args.abortRef.current = null;
  args.interruptSpeech();
  return { aborted: true };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && pnpm exec vitest run src/lib/chat/bargeIn.test.ts`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/chat/bargeIn.ts app/src/lib/chat/bargeIn.test.ts
git commit -m "feat(chat): add barge-in abort helpers"
```

---

### Task 3: ComposerWaveform component

**Files:**
- Create: `app/src/components/chat/ComposerWaveform.tsx`
- Test: `app/src/components/chat/ComposerWaveform.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComposerWaveform } from "./ComposerWaveform";

describe("ComposerWaveform", () => {
  it("renders bars with aria label for listening", () => {
    render(<ComposerWaveform level={0.5} active mode="listening" />);
    expect(screen.getByRole("img", { name: /listening/i })).toBeInTheDocument();
  });

  it("hides visually when inactive", () => {
    const { container } = render(
      <ComposerWaveform level={0} active={false} mode="listening" />,
    );
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && pnpm exec vitest run src/components/chat/ComposerWaveform.test.tsx`

Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```tsx
"use client";

import { cn } from "@/lib/utils";

const BAR_COUNT = 5;

export function ComposerWaveform({
  level,
  active,
  mode,
  className,
}: {
  level: number;
  active: boolean;
  mode: "listening" | "speaking";
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(1, level));
  const label = mode === "listening" ? "Listening level" : "Speaking level";

  return (
    <div
      role="img"
      aria-label={active ? label : undefined}
      aria-hidden={active ? undefined : true}
      className={cn(
        "flex h-4 items-end gap-0.5",
        !active && "opacity-0",
        className,
      )}
    >
      {Array.from({ length: BAR_COUNT }, (_, i) => {
        const peak = Math.max(0.15, clamped * (0.55 + ((i % 3) + 1) * 0.15));
        return (
          <span
            key={i}
            className={cn(
              "w-0.5 rounded-sm bg-ink-700 transition-[height] duration-75",
              mode === "speaking" && "bg-accent",
            )}
            style={{ height: `${Math.round(peak * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && pnpm exec vitest run src/components/chat/ComposerWaveform.test.tsx`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/src/components/chat/ComposerWaveform.tsx app/src/components/chat/ComposerWaveform.test.tsx
git commit -m "feat(chat): add composer waveform"
```

---

### Task 4: Toggle-only mic + waveform in ChatInterface

**Files:**
- Modify: `app/src/components/chat/ChatInterface.tsx`
- Use: `voiceCapture.ts`, `ComposerWaveform.tsx`, `audioLevel` from `useVoice`

- [ ] **Step 1: Replace hold handlers with toggle**

Remove `onPointerDown` / `onPointerUp` / `onPointerCancel` hold capture on the mic button.

Wire:

```tsx
const recordingStartedAtRef = useRef<number | null>(null);

const handleMicClick = async () => {
  if (!VOICE_FEATURE_ENABLED || voiceProcessing || pendingVoiceTranscript) return;
  if (isRecording) {
    const started = recordingStartedAtRef.current;
    recordingStartedAtRef.current = null;
    const elapsed = started ? Date.now() - started : MIN_VOICE_CAPTURE_MS;
    if (shouldDiscardVoiceCapture(elapsed)) {
      await cancelRecording();
      appendSystemNote("Hold a bit longer, or try again.");
      return;
    }
    await finishVoiceCapture(sendImmediately);
    return;
  }
  // Barge-in if streaming (Task 5 will fully own abort; call abort helper here too)
  setReplyModeAndPersist("voice");
  interruptSpeech();
  recordingStartedAtRef.current = Date.now();
  await startRecording();
};
```

Mic button:

```tsx
<button
  type="button"
  onClick={() => void handleMicClick()}
  onPointerEnter={() => void preconnectVoicePipeline()}
  aria-pressed={isRecording}
  aria-label={isRecording ? "Stop recording" : "Start voice message"}
  title={isRecording ? "Tap to stop" : "Tap to talk"}
  disabled={voiceProcessing || Boolean(pendingVoiceTranscript)}
  // do NOT disable solely for isStreaming — barge-in needs mic live
>
```

In the listening status strip, render:

```tsx
<ComposerWaveform
  level={audioLevel}
  active={isRecording || isPlaying}
  mode={isRecording ? "listening" : "speaking"}
/>
```

Destructure `audioLevel` from `useVoice()`.

Update coach copy: “Tap the mic to talk…”

Rename misleading `handleMicToggle` (today cancels only) to `cancelMic` if still needed.

- [ ] **Step 2: Typecheck**

Run: `cd app && pnpm typecheck`

Expected: PASS (or only pre-existing unrelated errors).

- [ ] **Step 3: Commit**

```bash
git add app/src/components/chat/ChatInterface.tsx
git commit -m "feat(chat): toggle mic with composer waveform"
```

---

### Task 5: Full barge-in on send + Stop + Esc

**Files:**
- Modify: `app/src/components/chat/ChatInterface.tsx`
- Use: `app/src/lib/chat/bargeIn.ts`

- [ ] **Step 1: Change sendMessage gate**

Replace:

```ts
if (!text.trim() || isStreaming || sendInFlightRef.current) return;
```

With:

```ts
if (!text.trim()) return;
if (shouldBargeIn({ isStreaming: isStreamingRef.current, sendInFlight: sendInFlightRef.current })) {
  abortActiveTurn({ abortRef, interruptSpeech });
  // Allow prior finally blocks to settle; then continue this turn.
  sendInFlightRef.current = false;
  setIsStreaming(false);
}
if (sendInFlightRef.current) return;
```

When aborting mid-stream with partial `streamingContent`, finalize into an assistant message (reuse existing `finalize` pattern) **before** clearing streaming state, so partial text is kept and not duplicated.

- [ ] **Step 2: Add Stop generation control**

When `isStreaming`, show a Stop button in the status/composer area that calls:

```ts
const stopGeneration = () => {
  abortActiveTurn({ abortRef, interruptSpeech });
  sendInFlightRef.current = false;
  setIsStreaming(false);
  // keep partial via finalize if streamingContent non-empty
};
```

- [ ] **Step 3: Esc key**

```ts
useEffect(() => {
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    if (isStreamingRef.current || isPlaying) {
      e.preventDefault();
      stopGeneration();
    }
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}, [stopGeneration, isPlaying]);
```

Ensure stream reader path treats `AbortError` as intentional (no scary toast / no streamRecovery for user abort). Inspect `sendMessage` catch block and skip recovery when `signal.aborted`.

- [ ] **Step 4: Enable send while streaming**

Remove `disabled={isStreaming}` from Send; keep spinner optional or switch icon to Stop when streaming with empty input.

- [ ] **Step 5: Typecheck + commit**

```bash
cd app && pnpm typecheck
git add app/src/components/chat/ChatInterface.tsx
git commit -m "feat(chat): full barge-in and stop generation"
```

---

### Task 6: Settings UI for auto-send vs review

**Files:**
- Modify: `app/src/components/chat/ChatInterface.tsx` (or extract into `ChatComposer` in Task 8)
- Use existing: `readSendImmediatelyOnRelease`, `storeSendImmediatelyOnRelease`, `readChatReplyMode`, `storeChatReplyMode`

- [ ] **Step 1: Add composer settings menu**

Use existing `@radix-ui/react-dropdown-menu` (already a dependency) or a small popover:

```tsx
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"; // if not present, use a simple details/summary menu to avoid new deps
```

If dropdown-menu shadcn wrapper is missing, implement a minimal `<details>` menu to stay YAGNI:

```tsx
<details className="relative">
  <summary className={BTN_COMPOSER_ICON} aria-label="Voice settings">⚙</summary>
  <div className="absolute bottom-full mb-2 ...">
    <p>After recording</p>
    <label>
      <input
        type="radio"
        checked={sendImmediately}
        onChange={() => {
          storeSendImmediatelyOnRelease(true);
          setSendImmediately(true);
        }}
      />
      Send immediately
    </label>
    <label>
      <input
        type="radio"
        checked={!sendImmediately}
        onChange={() => {
          storeSendImmediatelyOnRelease(false);
          setSendImmediately(false);
        }}
      />
      Review before send
    </label>
    <p>Aarya replies</p>
    {/* voice / text radios using setReplyModeAndPersist */}
  </div>
</details>
```

Ensure `sendImmediately` state is initialized from `readSendImmediatelyOnRelease()` (already present — confirm UI writes through `store*`).

- [ ] **Step 2: Manual sanity** — review mode shows `VoiceTranscriptReview` after toggle-stop.

- [ ] **Step 3: Commit**

```bash
git add app/src/components/chat/ChatInterface.tsx
git commit -m "feat(chat): voice settings for auto-send vs review"
```

---

### Task 7: TTS 10s guard (API + client)

**Files:**
- Modify: `api/src/hireloop_api/services/voice/deepgram_tts.py`
- Modify: `app/src/lib/hooks/useVoice.ts`
- Test: `api/tests/test_deepgram_tts_timeout.py`

- [ ] **Step 1: Write failing API test**

```python
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src/hireloop_api/services/voice/deepgram_tts.py"


def test_deepgram_tts_httpx_timeout_is_ten_seconds() -> None:
    text = SRC.read_text(encoding="utf-8")
    assert "timeout=10.0" in text or "timeout=10" in text
    assert "timeout=60.0" not in text
```

- [ ] **Step 2: Run to verify fail**

Run: `cd api && pytest tests/test_deepgram_tts_timeout.py -q`

Expected: FAIL (still 60.0).

- [ ] **Step 3: Change API timeout**

In `deepgram_tts.py`:

```python
async with httpx.AsyncClient(timeout=10.0) as client:
```

- [ ] **Step 4: Client TTS timeout + playback cap**

In `useVoice.ts` `speakDeepgram`:

```ts
{ timeoutMs: 10_000 },
```

Also add a playback wall clock:

```ts
const PLAYBACK_MAX_MS = 10_000;
const playbackTimer = setTimeout(() => settle({ stopAudio: true }), PLAYBACK_MAX_MS);
// clearTimeout in settle()
```

Export constant:

```ts
export const DEEPGRAM_TTS_TIMEOUT_MS = 10_000;
```

Update `getVoiceSupportStatus()` so TTS is available when Deepgram config is enabled **or** `speechSynthesis` exists (probe `/voice/config` already cached if present; at minimum treat `typeof Audio !== "undefined"` + synthesis OR always `tts: true` when STT path exists — prefer: `tts: Boolean(window.speechSynthesis) || true` when Deepgram key configured is unknown client-side; simplest fix matching spec: `tts: typeof Audio !== "undefined"`).

- [ ] **Step 5: Run tests**

```bash
cd api && pytest tests/test_deepgram_tts_timeout.py -q
cd app && pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add api/src/hireloop_api/services/voice/deepgram_tts.py api/tests/test_deepgram_tts_timeout.py app/src/lib/hooks/useVoice.ts
git commit -m "fix(voice): enforce 10s Deepgram TTS timeout"
```

---

### Task 8: AudioWorklet for live STT PCM

**Files:**
- Create: `app/public/worklets/pcm-capture-processor.js`
- Modify: `app/src/lib/hooks/useVoice.ts`

- [ ] **Step 1: Add worklet processor**

`app/public/worklets/pcm-capture-processor.js`:

```js
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input && input.length) {
      const copy = new Float32Array(input.length);
      copy.set(input);
      this.port.postMessage({ type: "audio", samples: copy }, [copy.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
```

- [ ] **Step 2: Replace ScriptProcessorNode path**

In live Deepgram `ws.onopen` handler inside `useVoice.ts`:

```ts
await ctx.audioWorklet.addModule("/worklets/pcm-capture-processor.js");
const worklet = new AudioWorkletNode(ctx, "pcm-capture-processor");
workletRef.current = worklet;
source.connect(worklet);
// Do not connect worklet to destination (no monitoring needed).

worklet.port.onmessage = (ev) => {
  const samples = ev.data?.samples as Float32Array | undefined;
  if (!samples) return;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  setAudioLevel(Math.min(1, Math.sqrt(sum / samples.length) * 3.2));
  if (ws.readyState === WebSocket.OPEN) {
    const pcm = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    ws.send(pcm.buffer);
  }
};
```

On teardown, disconnect/close worklet; keep `ScriptProcessorNode` **only** as fallback if `audioWorklet.addModule` throws (try/catch → existing processor path or batch).

Remove unused `processorRef` ScriptProcessor typing once fallback also cleaned, or keep for fallback.

- [ ] **Step 3: Typecheck**

Run: `cd app && pnpm typecheck`

- [ ] **Step 4: Commit**

```bash
git add app/public/worklets/pcm-capture-processor.js app/src/lib/hooks/useVoice.ts
git commit -m "feat(voice): capture live STT PCM via AudioWorklet"
```

---

### Task 9: Extract ChatComposer

**Files:**
- Create: `app/src/components/chat/ChatComposer.tsx`
- Modify: `app/src/components/chat/ChatInterface.tsx`

- [ ] **Step 1: Move composer JSX**

Move the `composerSlot` block (coach mark, status strip, waveform, transcript review, textarea, paperclip, send, mic, settings, hinglish hint, voice error) into `ChatComposer` with explicit props:

```ts
export type ChatComposerProps = {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onMicClick: () => void;
  onStopGeneration: () => void;
  onStartCareerCall: () => void;
  onResumeUpload: (file: File) => void;
  // voice/stream flags
  isStreaming: boolean;
  isRecording: boolean;
  isPlaying: boolean;
  voiceProcessing: boolean;
  audioLevel: number;
  interimTranscript: string;
  pendingVoiceTranscript: string | null;
  onPendingTranscriptChange: (v: string | null) => void;
  onSendVoiceTranscript: () => void;
  sendImmediately: boolean;
  onSendImmediatelyChange: (v: boolean) => void;
  replyMode: ChatReplyMode;
  onReplyModeChange: (m: ChatReplyMode) => void;
  hinglishHint: boolean;
  voiceError: string | null;
  showCoachMark: boolean;
  onDismissCoach: () => void;
  isUploading: boolean;
  composerInputDisabled: boolean;
  voiceEnabled: boolean;
};
```

`ChatInterface` keeps business logic; `ChatComposer` is presentational + local menu open state only.

- [ ] **Step 2: Typecheck + lint**

```bash
cd app && pnpm typecheck && pnpm lint
```

- [ ] **Step 3: Commit**

```bash
git add app/src/components/chat/ChatComposer.tsx app/src/components/chat/ChatInterface.tsx
git commit -m "refactor(chat): extract ChatComposer from ChatInterface"
```

---

### Task 10: In-thread career call

**Files:**
- Create: `app/src/components/chat/CareerCallConsent.tsx`
- Create: `app/src/components/chat/InThreadCallBanner.tsx`
- Modify: `app/src/components/chat/ChatInterface.tsx`
- Modify: `app/src/app/voice/VoiceSession.tsx` (extract shared loop helpers if needed, or embed slimmed logic)
- Modify: `app/src/app/dashboard/DashboardClient.tsx`
- Modify: `app/src/app/voice/page.tsx`
- Modify: `app/src/components/chat/VoiceDeepDiveModal.tsx`

- [ ] **Step 1: CareerCallConsent**

Lightweight confirm (reuse copy from `VoiceDeepDiveModal`): checkbox + Continue. Calls `onConfirm()`.

- [ ] **Step 2: InThreadCallBanner**

```tsx
export function InThreadCallBanner({
  secondsLeft,
  muted,
  audioLevel,
  onToggleMute,
  onEnd,
}: {
  secondsLeft: number;
  muted: boolean;
  audioLevel: number;
  onToggleMute: () => void;
  onEnd: () => void;
}) {
  // format mm:ss, waveform, Mute, End call
}
```

- [ ] **Step 3: Call mode state in ChatInterface**

```ts
const [careerCallActive, setCareerCallActive] = useState(false);
const [careerCallConsentOpen, setCareerCallConsentOpen] = useState(false);
```

Composer phone/call button → open consent → on confirm:
1. `startCareerCall(...)` from `@/lib/api/voiceSessions`
2. set `careerCallActive`
3. Run listen/speak loop (prefer extracting a `useCareerCallLoop` hook from `VoiceSession` patterns: continuous STT → `sendMessage(..., { contentType: "voice", voiceSessionId })` → TTS). **Minimum viable:** mount existing `VoiceSession` with `embedded` **inside** the chat column under the banner instead of a modal — but hide the full-screen chrome and show only banner controls if `VoiceSession` already supports `embedded`.

Preferred path matching spec “fold into thread”:

- Refactor `VoiceSession` to accept `variant="inline"` that renders **null chrome** and exposes imperative handle OR callbacks for timer/mute/level, while ChatInterface renders `InThreadCallBanner`.
- If that is too large in one step: first render `VoiceSession embedded` **below messages / above composer** (not Modal), then iterate banner.

**Do not** leave `VoiceDeepDiveModal` as the primary entry from composer.

- [ ] **Step 4: Wire dashboard entry**

`DashboardClient`: if `initialVoiceDeepDive` / search `careerCall=1`, set chat `initialCareerCall` instead of opening modal.

`/voice` page: `redirect` to `/dashboard?careerCall=1` (preserve query for scheduled session id if any).

- [ ] **Step 5: Typecheck**

```bash
cd app && pnpm typecheck
```

- [ ] **Step 6: Commit**

```bash
git add app/src/components/chat/CareerCallConsent.tsx \
  app/src/components/chat/InThreadCallBanner.tsx \
  app/src/components/chat/ChatInterface.tsx \
  app/src/components/chat/ChatComposer.tsx \
  app/src/app/voice/VoiceSession.tsx \
  app/src/app/voice/page.tsx \
  app/src/app/dashboard/DashboardClient.tsx \
  app/src/components/chat/VoiceDeepDiveModal.tsx
git commit -m "feat(chat): fold career call into the chat thread"
```

---

### Task 11: Verification sweep

- [ ] **Step 1: Run unit tests**

```bash
cd app && pnpm exec vitest run src/lib/chat/voiceCapture.test.ts src/lib/chat/bargeIn.test.ts src/components/chat/ComposerWaveform.test.tsx
cd api && pytest tests/test_deepgram_tts_timeout.py -q
```

Expected: all PASS

- [ ] **Step 2: Typecheck + lint app**

```bash
cd app && pnpm typecheck && pnpm lint
```

- [ ] **Step 3: Manual checklist** (document in commit message or PR notes)

1. Toggle mic → waveform moves → transcript auto-sends  
2. Settings → Review before send → edit panel appears  
3. Send while Aarya streaming → stream aborts, new turn starts  
4. Esc / Stop stops generation  
5. Start career call from composer → in-thread banner + conversation continues  
6. End call → banner gone, normal composer  

- [ ] **Step 4: Final commit if fixes needed**

```bash
git commit -m "chore(chat): verify chat voice UX upgrade"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Composer waveform | 3, 4 |
| Toggle-only mic | 4 |
| Min ~350ms discard | 1, 4 |
| Full barge-in | 2, 5 |
| Stop + Esc | 5 |
| Auto-send vs review settings | 6 |
| In-thread career call | 10 |
| TTS 10s client+API | 7 |
| AudioWorklet | 8 |
| Split ChatInterface / ChatComposer | 9 |
| Deprecate modal/`/voice` as primary | 10 |

## Out of scope (do not implement)

- Message queue
- Hold-to-talk dual mode
- Edit/resend last user message
- Zustand chat store
- Nitya / public profile voice
