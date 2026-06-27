"use client";

/**
 * VoiceSession — 15-min Aarya voice career session.
 *
 * Architecture (unified with text chat):
 *   Browser mic → STT (/api/v1/voice/stt or browser fallback)
 *     → streamAaryaMessage (shared SSE client, content_type=voice)
 *     → sentence-streaming TTS (Deepgram Aura or browser SpeechSynthesis)
 *   Same Aarya agent, memory, and tools as ChatInterface.
 *
 * Session unlock:
 *   On end → POST /api/v1/voice/sessions (status='completed')
 *   This writes a voice_sessions row → unlocks and redirects to /matches.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { streamAaryaMessage, ensureAaryaSession, prefetchAaryaWarmup, readStoredAaryaSession, storeAaryaSession } from "@/lib/chat/aaryaStream";
import { formatStatusWithEta } from "@/lib/chat/voiceStatus";
import { warmupChatContext } from "@/lib/chat/warmup";
import { useVoice, getVoiceSupportStatus } from "@/lib/hooks/useVoice";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

type TurnState =
  | "idle"           // before call starts
  | "starting"       // creating chat session
  | "aarya_speaking" // TTS playing
  | "user_listening" // mic open, waiting for user
  | "processing"     // streaming Aarya's reply
  | "ending"         // recording session + redirecting
  | "done";

interface VoiceSessionProps {
  candidateName?: string;
  fromOnboarding?: boolean;
  /** When set, render inside a modal/sheet and call back instead of navigating away. */
  embedded?: boolean;
  onComplete?: () => void;
}

// ── Component ────────────────────────────────────────────────────────────────

export function VoiceSession({
  candidateName,
  fromOnboarding,
  embedded = false,
  onComplete,
}: VoiceSessionProps) {
  const router = useRouter();
  const {
    startRecording,
    stopRecording,
    speak,
    speakFiller,
    stopSpeaking,
    isPlaying,
    interimTranscript,
    audioLevel,
  } = useVoice();

  const [turnState, setTurnState]     = useState<TurnState>("idle");
  const [transcript, setTranscript]   = useState<string>("");  // last user utterance
  const [aaryaText, setAaryaText]     = useState<string>("");  // last Aarya reply
  const [errorMsg, setErrorMsg]       = useState<string | null>(null);
  const [elapsedSecs, setElapsedSecs] = useState(0);
  const [micMuted, setMicMuted]       = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [streamRecovery, setStreamRecovery] = useState<string | null>(null);
  const lastJobsRef = useRef<Array<{ title?: string; company_name?: string | null }>>([]);

  // Refs (mutable, no re-render needed)
  const sessionIdRef    = useRef<string | null>(null);
  const startTimeRef    = useRef<Date | null>(null);
  const timerRef        = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef        = useRef<AbortController | null>(null);
  const isEndingRef     = useRef(false); // guard against double-end
  // Lets listenForUser call the latest doTurn without a useCallback dep cycle.
  const doTurnRef       = useRef<((c: string, t: string) => Promise<void>) | null>(null);

  // Browser support check
  const voiceSupport = typeof window !== "undefined" ? getVoiceSupportStatus() : "unsupported";
  const canSpeak   = voiceSupport !== "unsupported";
  const canListen  = voiceSupport === "supported" || voiceSupport === "stt_only";

  // ── Helpers ───────────────────────────────────────────────────────────────

  /**
   * Stream a message through Aarya, return the full reply text.
   * `onSentence` fires for each COMPLETE sentence as it streams in, so TTS can
   * start speaking while the rest of the reply is still generating — this is
   * what kills the long dead air on voice calls.
   */
  const streamAaryaReply = useCallback(
    async (
      userText: string,
      conversationId: string,
      onSentence?: (sentence: string) => void
    ): Promise<string> => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let emittedUpTo = 0;
      const emitCompleteSentences = (text: string, flush = false) => {
        if (!onSentence) return;
        const pending = text.slice(emittedUpTo);
        const re = /[.!?…]+["')\]]*\s+/g;
        let lastEnd = 0;
        let m: RegExpExecArray | null;
        while ((m = re.exec(pending)) !== null) {
          const candidate = pending.slice(lastEnd, m.index + m[0].length);
          if (candidate.trim().length >= 12) {
            onSentence(candidate.trim());
            lastEnd = m.index + m[0].length;
          }
        }
        emittedUpTo += lastEnd;
        if (flush) {
          const tail = text.slice(emittedUpTo).trim();
          if (tail) onSentence(tail);
          emittedUpTo = text.length;
        }
      };

      let accumulated = "";
      const result = await streamAaryaMessage(
        conversationId,
        userText,
        "voice",
        {
          onStatus: (status, meta) => {
            setStreamStatus(formatStatusWithEta(status, meta?.etaSec));
            if (meta?.spokenFiller) speakFiller(meta.spokenFiller);
          },
          onJobs: (jobs) => {
            lastJobsRef.current = jobs;
          },
          onText: (_chunk, full) => {
            setStreamStatus(null);
            accumulated = full;
            setAaryaText(full);
            emitCompleteSentences(full);
          },
        },
        ctrl.signal
      );
      accumulated = result.text;
      if (result.jobs.length > 0) lastJobsRef.current = result.jobs;

      emitCompleteSentences(accumulated, true);
      abortRef.current = null;
      setStreamRecovery(null);
      return accumulated;
    },
    [speakFiller]
  );

  /** Open the mic, wait for the user's utterance, then drive the next turn. */
  const listenForUser = useCallback(
    async (conversationId: string): Promise<void> => {
      if (isEndingRef.current) return;

      if (!canListen || micMuted) {
        // Fallback: no STT (or muted) — keep waiting; the end-call button and
        // the mic-tap control stay available.
        setTurnState("user_listening");
        return;
      }

      setTurnState("user_listening");
      setIsListening(true);
      setStreamStatus(null);
      try {
        await startRecording();
        // Auto-stop after 30s of silence (SpeechRecognition times out anyway)
        await new Promise<void>((res) => setTimeout(res, 30_000));
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setErrorMsg((err as Error).message);
        }
        setIsListening(false);
        return;
      }

      const userTranscript = await stopRecording();
      setIsListening(false);
      setTranscript(userTranscript);

      if (!userTranscript.trim() || isEndingRef.current) {
        if (!isEndingRef.current) {
          setErrorMsg(
            "I didn’t catch that — try once more, or tap end call if you’re done."
          );
          await new Promise<void>((res) => setTimeout(res, 1200));
          await listenForUser(conversationId);
        }
        return;
      }

      setErrorMsg(null);

      void doTurnRef.current?.(conversationId, userTranscript);
    },
    [canListen, micMuted, startRecording, stopRecording]
  );

  /** One full turn: stream Aarya's reply → speak it → hand the mic back. */
  const doTurn = useCallback(
    async (conversationId: string, triggerText: string): Promise<void> => {
      if (isEndingRef.current) return;

      // ── Aarya thinks (and starts speaking mid-stream) ─────────────────────
      setTurnState("processing");
      setStreamStatus("Aarya is thinking…");
      setAaryaText("");
      setTranscript("");

      // Sentence-streaming TTS: each complete sentence is appended to a serial
      // speech chain the moment it arrives, so Aarya starts talking ~1-2s into
      // generation instead of after the whole reply (was the main dead air).
      let speechChain: Promise<void> = Promise.resolve();
      let startedSpeaking = false;
      const queueSentence = (sentence: string) => {
        if (!canSpeak || isEndingRef.current) return;
        if (!startedSpeaking) {
          startedSpeaking = true;
          setTurnState("aarya_speaking");
        }
        speechChain = speechChain.then(() =>
          isEndingRef.current ? undefined : speak(sentence, "aarya").catch(() => undefined)
        );
      };

      try {
        await streamAaryaReply(triggerText, conversationId, queueSentence);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setStreamRecovery("Connection dropped — tap the mic when you're ready to continue.");
        setErrorMsg("Couldn't reach Aarya. Tap the mic to retry.");
        if (sessionIdRef.current) {
          await listenForUser(sessionIdRef.current);
        }
        return;
      }

      if (isEndingRef.current) return;

      // ── Wait for the speech queue to finish ───────────────────────────────
      setTurnState("aarya_speaking");
      await speechChain;

      if (isEndingRef.current) return;

      // ── User's turn ───────────────────────────────────────────────────────
      await listenForUser(conversationId);
    },
    [canSpeak, streamAaryaReply, speak, listenForUser]
  );

  // Keep the ref pointed at the latest doTurn so listenForUser can recurse
  // into it without a circular useCallback dependency.
  useEffect(() => {
    doTurnRef.current = doTurn;
  }, [doTurn]);

  // Pre-warm on mount: voice config, profile, top matches, chat session.
  useEffect(() => {
    void prefetchAaryaWarmup().catch(() => undefined);
    void warmupChatContext().catch(() => undefined);
    void apiAuthFetch("/api/v1/voice/config").catch(() => undefined);
  }, []);

  // ── Call lifecycle ────────────────────────────────────────────────────────

  const startCall = useCallback(async () => {
    setErrorMsg(null);
    isEndingRef.current = false;
    setElapsedSecs(0);

    const firstName = candidateName?.split(" ")[0] ?? "there";
    // A real senior recruiter picking up the phone — warm, in control, and it
    // ends on an open question so the candidate knows it's their turn.
    const greeting =
      `Hi ${firstName}, this is Aarya — I'm a senior recruiter here at Hireloop. ` +
      `Thanks for hopping on. I've got about fifteen minutes blocked to really understand ` +
      `your background and what you want next, and then I'll line up the roles that genuinely fit. ` +
      `So, to kick us off — tell me a bit about what you're doing right now, and where you'd love to go from here.`;

    // ── 0-second start ────────────────────────────────────────────────────────
    // The call "connects" instantly: start the timer and speak the greeting out
    // loud right away, while the backend chat session is created IN PARALLEL.
    // We no longer wait on the LLM before any audio plays — that was the dead air.
    startTimeRef.current = new Date();
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => setElapsedSecs((s) => s + 1), 1000);

    setTurnState("aarya_speaking");
    setTranscript("");
    setAaryaText(greeting);

    // Create the session without blocking the greeting on the round-trip.
    const sessionPromise = (async () => {
      const id = await ensureAaryaSession(readStoredAaryaSession(), storeAaryaSession);
      sessionIdRef.current = id;
    })();

    // Speak immediately — this is the instant "pickup".
    if (canSpeak) {
      try {
        await speak(greeting, "aarya");
      } catch {
        // TTS hiccup is non-fatal — fall through and still hand over the mic.
      }
    }

    // Greeting delivered — make sure the session exists before the user replies.
    try {
      await sessionPromise;
    } catch (err) {
      setErrorMsg((err as Error).message ?? "Couldn't connect to Aarya");
      if (timerRef.current) clearInterval(timerRef.current);
      setTurnState("idle");
      return;
    }

    if (isEndingRef.current) return;
    await listenForUser(sessionIdRef.current!);
  }, [candidateName, canSpeak, speak, listenForUser]);

  const endCall = useCallback(async () => {
    if (isEndingRef.current) return;
    isEndingRef.current = true;
    setTurnState("ending");
    setErrorMsg(null);  // clear any "didn't catch that" hint as we wrap up

    // Stop any in-flight operations
    stopSpeaking();
    abortRef.current?.abort();
    if (timerRef.current) clearInterval(timerRef.current);

    const duration = startTimeRef.current
      ? Math.round((Date.now() - startTimeRef.current.getTime()) / 1000)
      : elapsedSecs;

    // Record session → unlocks /matches gate
    try {
      await apiAuthFetch("/api/v1/voice/sessions", {
        method: "POST",
        body: JSON.stringify({
          conversation_id: sessionIdRef.current,
          duration_seconds: duration,
          status: "completed",
        }),
      });
    } catch {
      // Non-fatal — matches gate may stay locked until retry
    }

    if (fromOnboarding) {
      try {
        await apiAuthFetch("/api/v1/me/complete-onboarding", {
          method: "POST",
          body: JSON.stringify({ skipped_voice: false }),
        });
      } catch {
        /* non-fatal */
      }
    }

    setTurnState("done");
    try {
      sessionStorage.setItem(
        "hireloop_voice_session_summary",
        JSON.stringify({
          conversationId: sessionIdRef.current,
          durationSeconds: duration,
          jobCount: lastJobsRef.current.length,
        })
      );
    } catch {
      /* ignore */
    }
    setTimeout(() => {
      if (embedded && onComplete) {
        onComplete();
      } else {
        router.push("/dashboard?voice=done");
      }
    }, 1200);
  }, [elapsedSecs, embedded, fromOnboarding, onComplete, router, stopSpeaking]);

  /** Tap mic: barge-in while Aarya speaks, or force-stop capture while listening */
  const handleMicTap = useCallback(async () => {
    if (turnState === "aarya_speaking" || (turnState === "processing" && isPlaying)) {
      stopSpeaking();
      abortRef.current?.abort();
      if (sessionIdRef.current) {
        setTurnState("user_listening");
        await listenForUser(sessionIdRef.current);
      }
      return;
    }
    if (turnState === "user_listening" && isListening) {
      const text = await stopRecording();
      setIsListening(false);
      setTranscript(text);
      if (text.trim() && sessionIdRef.current) {
        void doTurn(sessionIdRef.current, text);
      } else if (sessionIdRef.current) {
        setErrorMsg("I didn't catch that — trying again…");
        await new Promise<void>((res) => setTimeout(res, 800));
        await listenForUser(sessionIdRef.current);
      }
    }
  }, [turnState, isListening, isPlaying, stopRecording, stopSpeaking, doTurn, listenForUser]);

  const toggleMute = useCallback(() => setMicMuted((v) => !v), []);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopSpeaking();
      abortRef.current?.abort();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [stopSpeaking]);

  // ── Derived UI state ──────────────────────────────────────────────────────

  const isActive     = turnState !== "idle" && turnState !== "starting" && turnState !== "done" && turnState !== "ending";
  const isConnecting = turnState === "starting";
  const isDone       = turnState === "done" || turnState === "ending";
  const formattedTime = `${String(Math.floor(elapsedSecs / 60)).padStart(2, "0")}:${String(elapsedSecs % 60).padStart(2, "0")}`;

  const statusLabel: Record<TurnState, string> = {
    idle:           "Ready to start",
    starting:       "Connecting to Aarya…",
    aarya_speaking: "Aarya is speaking…",
    user_listening: "Your turn — speak now",
    processing:     "Aarya is thinking…",
    ending:         "Saving session…",
    done:           embedded ? "Session complete" : "Session complete — heading to dashboard",
  };
  const visibleStatus = streamStatus ?? statusLabel[turnState];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center px-5 py-12",
        embedded ? "min-h-0 py-6" : "min-h-screen bg-paper-0",
      )}
    >
      <div className="max-w-sm w-full flex flex-col items-center gap-8">

        {/* ── Aarya avatar + animated rings ────────────────────────────── */}
        <div className="relative flex items-center justify-center">
          {/* Outer pulse when Aarya is speaking */}
          {turnState === "aarya_speaking" && isPlaying && (
            <>
              <span className="absolute w-36 h-36 rounded-full bg-ink-900/10 animate-ping"
                    style={{ animationDuration: "1.2s" }} />
              <span className="absolute w-28 h-28 rounded-full bg-ink-900/15 animate-ping"
                    style={{ animationDuration: "0.9s" }} />
            </>
          )}
          {/* Inner ring when listening */}
          {turnState === "user_listening" && (
            <span className="absolute w-24 h-24 rounded-full border-2 border-accent animate-pulse" />
          )}
          {/* Avatar */}
          <div className={cn(
            "w-20 h-20 rounded-full flex items-center justify-center text-paper-0 font-semibold text-h1 transition-all duration-300 shadow-2",
            isActive ? "bg-ink-900" : "bg-ink-700"
          )}>
            A
          </div>
        </div>

        {/* ── Status ────────────────────────────────────────────────────── */}
        <div className="text-center space-y-1">
          <h1 className="text-h2 font-semibold text-ink-900">
            {isActive || isConnecting ? "Aarya" : "Talk to Aarya"}
          </h1>
          {isActive && (
            <p className="text-small font-mono text-ink-500">{formattedTime}</p>
          )}
          <p className={cn("text-small transition-colors", isActive ? "text-ink-700" : "text-ink-500")}>
            {visibleStatus}
          </p>
        </div>

        {/* ── Waveform bars ─────────────────────────────────────────────── */}
        {/* While the user speaks, bar heights track the real mic level
            (audioLevel 0..1). While Aarya speaks, they animate on a loop. */}
        {isActive && (
          <div className="flex items-center justify-center gap-1 h-8" aria-hidden>
            {Array.from({ length: 12 }).map((_, i) => {
              const isUserTurn   = turnState === "user_listening";
              const isAaryaTurn  = turnState === "aarya_speaking" && isPlaying;
              // Symmetric envelope: center bars react more than the edges.
              const centerBias   = 1 - Math.abs(i - 5.5) / 6; // ~0..1
              const liveHeight   = 6 + audioLevel * 26 * (0.45 + centerBias * 0.55);
              return (
                <span
                  key={i}
                  className={cn(
                    "w-1.5 rounded-full transition-all duration-100",
                    isAaryaTurn
                      ? "bg-ink-900 animate-voice-bar"
                      : isUserTurn
                      ? "bg-accent"
                      : "bg-ink-200"
                  )}
                  style={{
                    animationDelay:    isAaryaTurn ? `${(i % 4) * 0.12}s` : undefined,
                    animationDuration: isAaryaTurn ? `${0.6 + (i % 3) * 0.2}s` : undefined,
                    height: isUserTurn
                      ? `${liveHeight}px`
                      : isAaryaTurn
                      ? undefined
                      : "6px",
                  }}
                />
              );
            })}
          </div>
        )}

        {/* ── Live transcript pane ──────────────────────────────────────── */}
        {/* Real-time preview: Aarya's reply streams in as she thinks, and the
            user's own words appear live (interimTranscript) while they speak. */}
        {(() => {
          const listening   = turnState === "user_listening";
          // Prefer the live interim caption while listening; fall back to the
          // settled transcript from the previous turn otherwise.
          const youText     = listening ? (interimTranscript || transcript) : transcript;
          const showYou     = listening || !!transcript;
          if (!isActive || (!aaryaText && !youText && !listening)) return null;
          return (
            <div className="w-full space-y-2" aria-live="polite">
              {aaryaText && (
                <div className="bg-paper-1 border border-ink-100 rounded-xl px-4 py-3">
                  <p className="text-micro text-ink-400 uppercase tracking-wide mb-1">Aarya</p>
                  <p className="text-small text-ink-900 leading-relaxed">{aaryaText}</p>
                </div>
              )}
              {showYou && (
                <div className="bg-ink-50 border border-ink-100 rounded-xl px-4 py-3">
                  <p className="text-micro text-ink-400 uppercase tracking-wide mb-1 flex items-center gap-1.5">
                    You
                    {listening && (
                      <span className="inline-flex items-center gap-1 text-accent normal-case tracking-normal">
                        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                        listening
                      </span>
                    )}
                  </p>
                  {youText ? (
                    <p className="text-small text-ink-700 leading-relaxed">
                      {youText}
                      {listening && interimTranscript && (
                        <span className="inline-block w-0.5 h-3.5 bg-accent/70 ml-0.5 align-middle animate-pulse" />
                      )}
                    </p>
                  ) : (
                    <p className="text-small text-ink-400 italic leading-relaxed">
                      Start speaking — your words will show up here…
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* ── Error ────────────────────────────────────────────────────── */}
        {errorMsg && (
          <div className="w-full bg-destructive-bg border border-destructive/30 rounded-xl px-4 py-3 text-small text-destructive text-center">
            {errorMsg}
          </div>
        )}

        {/* ── Browser support warning ───────────────────────────────────── */}
        {!canListen && turnState === "idle" && (
          <div className="w-full bg-ink-50 border border-ink-200 rounded-xl px-4 py-3 text-small text-ink-700 text-center">
            Voice input requires Chrome or Edge. You can still listen to Aarya and type your responses in the dashboard chat.
          </div>
        )}

        {/* ── Controls ─────────────────────────────────────────────────── */}
        <div className="flex items-center justify-center gap-5">

          {/* Mute — only during active call */}
          {isActive && canListen && (
            <button
              type="button"
              onClick={toggleMute}
              title={micMuted ? "Unmute mic" : "Mute mic"}
              className={cn(
                "w-14 h-14 rounded-full flex items-center justify-center transition-colors",
                micMuted ? "bg-destructive/10 text-destructive" : "bg-ink-100 text-ink-600 hover:bg-ink-200"
              )}
            >
              {micMuted ? <MicOff className="h-5 w-5" strokeWidth={1.5} /> : <Mic className="h-5 w-5" strokeWidth={1.5} />}
            </button>
          )}

          {/* Tap mic to stop listening early */}
          {turnState === "user_listening" && isListening && (
            <button
              type="button"
              onClick={() => void handleMicTap()}
              title="Done speaking — send"
              className="w-16 h-16 rounded-full bg-accent text-paper-0 flex items-center justify-center shadow-2 hover:bg-accent-hover transition-all"
            >
              <Mic className="h-6 w-6" strokeWidth={1.5} />
            </button>
          )}

          {/* Start button — idle */}
          {turnState === "idle" && (
            <button
              type="button"
              onClick={() => void startCall()}
              className="w-20 h-20 rounded-full bg-ink-900 hover:bg-ink-800 text-paper-0 flex items-center justify-center shadow-lg transition-all hover:scale-105 active:scale-95"
              aria-label="Start call with Aarya"
            >
              <Mic className="h-7 w-7" strokeWidth={1.5} />
            </button>
          )}

          {/* Connecting spinner */}
          {isConnecting && (
            <div className="w-20 h-20 rounded-full bg-ink-200 flex items-center justify-center">
              <div className="w-7 h-7 rounded-full border-2 border-ink-500 border-t-transparent animate-spin" />
            </div>
          )}

          {/* End call — active */}
          {isActive && (
            <button
              type="button"
              onClick={() => void endCall()}
              title="End session"
              className="w-14 h-14 rounded-full bg-destructive text-paper-0 flex items-center justify-center shadow-2 hover:bg-red-700 transition-all hover:scale-105"
            >
              <PhoneOff className="h-5 w-5" strokeWidth={1.5} />
            </button>
          )}

          {/* Ending/done spinner */}
          {isDone && (
            <div className="w-20 h-20 rounded-full bg-ink-100 flex items-center justify-center">
              <div className="w-7 h-7 rounded-full border-2 border-ink-400 border-t-transparent animate-spin" />
            </div>
          )}
        </div>

        {/* ── Context text — idle only ───────────────────────────────────── */}
        {turnState === "idle" && (
          <div className="text-center space-y-1.5">
            <p className="text-body text-ink-700 font-medium">
              Hi{candidateName ? `, ${candidateName.split(" ")[0]}` : ""}!
            </p>
            <p className="text-small text-ink-500 leading-relaxed max-w-xs">
              Aarya will guide you through a 15-minute conversation about your
              career goals — then start finding you the best matches in India.
              No typing needed.
            </p>
          </div>
        )}

        {/* ── Back link — idle only ─────────────────────────────────────── */}
        {turnState === "idle" && (
          <button
            type="button"
            onClick={() => router.back()}
            className="text-small text-ink-400 hover:text-ink-700 transition-colors underline underline-offset-2"
          >
            Not now, go back
          </button>
        )}
      </div>
    </div>
  );
}
