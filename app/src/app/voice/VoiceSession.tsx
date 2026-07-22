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
 * Career-call lifecycle is durable: the server owns start/resume/completion,
 * while this component owns only the browser microphone, timer, and playback.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff } from "@/components/brand/icons";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { markClientOnboardingComplete } from "@/lib/auth/onboarding-complete";
import { createClient } from "@/lib/supabase/client";
import { completeCareerCall, startCareerCall } from "@/lib/api/voiceSessions";
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
  | "save_failed"    // local media stopped; server completion needs retry
  | "done";

type VoiceSessionProps = {
  candidateName?: string;
  fromOnboarding?: boolean;
  consent: boolean;
  scheduledSessionId?: string;
  /** When set, render inside a modal/sheet and call back instead of navigating away. */
  embedded?: boolean;
  onComplete?: () => void;
};

const CALL_SECONDS = 15 * 60;
const WRAP_WARNING_SECONDS = 14 * 60;
const MAX_RECORDED_SECONDS = 16 * 60;

type CompletionReason = Parameters<typeof completeCareerCall>[1]["completionReason"];

// ── Component ────────────────────────────────────────────────────────────────

export function VoiceSession({
  candidateName,
  fromOnboarding,
  consent,
  scheduledSessionId,
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
  const [, setStreamRecovery] = useState<string | null>(null);
  const lastJobsRef = useRef<Array<{ title?: string; company_name?: string | null }>>([]);

  // Refs (mutable, no re-render needed)
  const conversationIdRef = useRef<string | null>(null);
  const voiceSessionIdRef = useRef<string | null>(null);
  const startTimeRef    = useRef<number | null>(null);
  const timerRef        = useRef<ReturnType<typeof setInterval> | null>(null);
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listenTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const releaseListenWaitRef = useRef<(() => void) | null>(null);
  const abortRef        = useRef<AbortController | null>(null);
  const isEndingRef     = useRef(false); // guard against double-end
  const isMountedRef = useRef(true);
  const startInFlightRef = useRef(false);
  const completionInFlightRef = useRef(false);
  const recordingActiveRef = useRef(false);
  const recordingStartingRef = useRef(false);
  const recordingStartPromiseRef = useRef<Promise<void> | null>(null);
  const recordingStoppingRef = useRef(false);
  const recordingStopPromiseRef = useRef<Promise<string> | null>(null);
  const captureCycleInFlightRef = useRef(false);
  const discardCaptureRef = useRef(false);
  const listeningParkedRef = useRef(false);
  const resumeAfterDiscardRef = useRef(false);
  const micMutedRef = useRef(false);
  const pendingCompletionRef = useRef<{
    durationSeconds: number;
    completionReason: CompletionReason;
  } | null>(null);
  const timeLimitTriggeredRef = useRef(false);
  const endCallRef = useRef<((reason: CompletionReason) => Promise<void>) | null>(null);
  // Lets listenForUser call the latest doTurn without a useCallback dep cycle.
  const doTurnRef       = useRef<((c: string, t: string) => Promise<void>) | null>(null);

  // Browser support check
  const voiceSupport = typeof window !== "undefined" ? getVoiceSupportStatus() : "unsupported";
  const canSpeak   = voiceSupport !== "unsupported";
  const canListen  = voiceSupport === "supported" || voiceSupport === "stt_only";

  const stopRecordingOnce = useCallback(async (): Promise<string> => {
    if (recordingStopPromiseRef.current) return recordingStopPromiseRef.current;
    if (!recordingActiveRef.current) return "";

    recordingActiveRef.current = false;
    recordingStoppingRef.current = true;
    const stopPromise = stopRecording().catch(() => "");
    recordingStopPromiseRef.current = stopPromise;
    try {
      return await stopPromise;
    } finally {
      if (recordingStopPromiseRef.current === stopPromise) {
        recordingStopPromiseRef.current = null;
        recordingStoppingRef.current = false;
      }
    }
  }, [stopRecording]);

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
    ): Promise<{ text: string; coverageComplete: boolean }> => {
      const voiceSessionId = voiceSessionIdRef.current;
      if (!voiceSessionId) throw new Error("The career call has not started yet.");
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
        ctrl.signal,
        { voiceSessionId }
      );
      accumulated = result.text;
      if (result.jobs.length > 0) lastJobsRef.current = result.jobs;

      emitCompleteSentences(accumulated, true);
      if (abortRef.current === ctrl) abortRef.current = null;
      setStreamRecovery(null);
      return { text: accumulated, coverageComplete: result.coverageComplete };
    },
    [speakFiller]
  );

  /** Open the mic, wait for the user's utterance, then drive the next turn. */
  const listenForUser = useCallback(
    async (conversationId: string): Promise<void> => {
      if (isEndingRef.current || !isMountedRef.current) return;

      if (!canListen || micMutedRef.current) {
        // Fallback: no STT (or muted) — keep waiting; the end-call button and
        // the mic-tap control stay available.
        listeningParkedRef.current = true;
        setTurnState("user_listening");
        return;
      }
      if (
        captureCycleInFlightRef.current ||
        recordingStartingRef.current ||
        recordingActiveRef.current ||
        recordingStoppingRef.current
      ) return;

      listeningParkedRef.current = false;
      captureCycleInFlightRef.current = true;
      recordingStartingRef.current = true;
      setTurnState("user_listening");
      setIsListening(true);
      setStreamStatus(null);
      try {
        const startPromise = startRecording();
        recordingStartPromiseRef.current = startPromise;
        await startPromise;
        if (recordingStartPromiseRef.current === startPromise) {
          recordingStartPromiseRef.current = null;
          recordingStartingRef.current = false;
        }
        recordingActiveRef.current = true;
        if (
          isEndingRef.current ||
          !isMountedRef.current ||
          micMutedRef.current ||
          discardCaptureRef.current
        ) {
          await stopRecordingOnce();
          discardCaptureRef.current = false;
          if (isMountedRef.current && !isEndingRef.current) {
            setIsListening(false);
            setTurnState("user_listening");
            listeningParkedRef.current = true;
            if (resumeAfterDiscardRef.current && !micMutedRef.current) {
              resumeAfterDiscardRef.current = false;
              listeningParkedRef.current = false;
              captureCycleInFlightRef.current = false;
              void Promise.resolve().then(() => listenForUser(conversationId));
            } else {
              captureCycleInFlightRef.current = false;
            }
          } else {
            captureCycleInFlightRef.current = false;
          }
          return;
        }

        // The mic button releases this wait early; otherwise capture ends after
        // 30 seconds. One owner then stops STT and dispatches exactly one turn.
        await new Promise<void>((resolve) => {
          releaseListenWaitRef.current = resolve;
          listenTimerRef.current = setTimeout(resolve, 30_000);
        });
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          if (isMountedRef.current) setErrorMsg((err as Error).message);
        }
        recordingStartPromiseRef.current = null;
        recordingStartingRef.current = false;
        recordingActiveRef.current = false;
        captureCycleInFlightRef.current = false;
        if (isMountedRef.current) setIsListening(false);
        return;
      }

      if (listenTimerRef.current) clearTimeout(listenTimerRef.current);
      listenTimerRef.current = null;
      releaseListenWaitRef.current = null;

      if (
        !recordingActiveRef.current &&
        !recordingStopPromiseRef.current &&
        !discardCaptureRef.current
      ) {
        captureCycleInFlightRef.current = false;
        if (isMountedRef.current) setIsListening(false);
        return;
      }
      const userTranscript = await stopRecordingOnce();
      if (!isMountedRef.current) {
        captureCycleInFlightRef.current = false;
        return;
      }
      setIsListening(false);

      if (isEndingRef.current) {
        captureCycleInFlightRef.current = false;
        return;
      }
      const discardCapture = discardCaptureRef.current || micMutedRef.current;
      discardCaptureRef.current = false;
      if (discardCapture) {
        setTurnState("user_listening");
        listeningParkedRef.current = true;
        if (resumeAfterDiscardRef.current && !micMutedRef.current) {
          resumeAfterDiscardRef.current = false;
          listeningParkedRef.current = false;
          captureCycleInFlightRef.current = false;
          void Promise.resolve().then(() => listenForUser(conversationId));
        } else {
          captureCycleInFlightRef.current = false;
        }
        return;
      }
      captureCycleInFlightRef.current = false;
      setTranscript(userTranscript);

      if (!userTranscript.trim()) {
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
    [canListen, startRecording, stopRecordingOnce]
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
      let coverageComplete = false;
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
        const result = await streamAaryaReply(triggerText, conversationId, queueSentence);
        coverageComplete = result.coverageComplete;
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setStreamRecovery("Connection dropped — tap the mic when you're ready to continue.");
        setErrorMsg("Couldn't reach Aarya. Tap the mic to retry.");
        if (conversationIdRef.current) {
          await listenForUser(conversationIdRef.current);
        }
        return;
      }

      if (isEndingRef.current) return;

      // ── Wait for the speech queue to finish ───────────────────────────────
      setTurnState("aarya_speaking");
      await speechChain;

      if (isEndingRef.current) return;

      // The backend sends this only after the private wrap reply is durable.
      // Complete this exact call after speech, without reopening the mic.
      if (coverageComplete) {
        await endCallRef.current?.("coverage_complete");
        return;
      }

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

  const clearCallTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  }, []);

  const stopLocalMedia = useCallback(async () => {
    stopSpeaking();
    abortRef.current?.abort();
    abortRef.current = null;
    releaseListenWaitRef.current?.();
    releaseListenWaitRef.current = null;
    if (listenTimerRef.current) clearTimeout(listenTimerRef.current);
    listenTimerRef.current = null;
    await recordingStartPromiseRef.current?.catch(() => undefined);
    await stopRecordingOnce();
    if (isMountedRef.current) setIsListening(false);
  }, [stopRecordingOnce, stopSpeaking]);

  const finishCompletedCall = useCallback(
    async (durationSeconds: number) => {
      if (fromOnboarding) {
        try {
          await apiAuthFetch("/api/v1/me/complete-onboarding", {
            method: "POST",
            body: JSON.stringify({ skipped_voice: false }),
          });
          const { data: authData } = await createClient().auth.getUser();
          markClientOnboardingComplete(authData.user?.id);
        } catch {
          /* Career-call completion remains authoritative. */
        }
      }

      if (!isMountedRef.current) return;
      setTurnState("done");
      try {
        sessionStorage.setItem(
          "hireloop_voice_session_summary",
          JSON.stringify({
            conversationId: conversationIdRef.current,
            durationSeconds,
            jobCount: lastJobsRef.current.length,
          })
        );
      } catch {
        /* Browser storage is optional. */
      }
      redirectTimerRef.current = setTimeout(() => {
        if (!isMountedRef.current) return;
        if (embedded && onComplete) onComplete();
        else router.push("/dashboard?kickoff=career");
      }, 1200);
    },
    [embedded, fromOnboarding, onComplete, router]
  );

  const persistCompletion = useCallback(async () => {
    const voiceSessionId = voiceSessionIdRef.current;
    const completion = pendingCompletionRef.current;
    if (!voiceSessionId || !completion || completionInFlightRef.current) return;

    completionInFlightRef.current = true;
    if (isMountedRef.current) {
      setTurnState("ending");
      setErrorMsg(null);
    }
    try {
      await completeCareerCall(voiceSessionId, completion);
      pendingCompletionRef.current = null;
      await finishCompletedCall(completion.durationSeconds);
    } catch (error) {
      if (isMountedRef.current) {
        setErrorMsg(
          `${(error as Error).message || "Aarya couldn't save the call."} Your call is still active on the server. Retry saving to finish.`
        );
        setTurnState("save_failed");
      }
    } finally {
      completionInFlightRef.current = false;
    }
  }, [finishCompletedCall]);

  const endCall = useCallback(
    async (completionReason: CompletionReason) => {
      if (
        isEndingRef.current ||
        pendingCompletionRef.current ||
        completionInFlightRef.current
      ) return;
      const voiceSessionId = voiceSessionIdRef.current;
      if (!voiceSessionId) {
        if (isMountedRef.current) setErrorMsg("Start the call before trying to finish it.");
        return;
      }

      isEndingRef.current = true;
      if (isMountedRef.current) {
        setTurnState("ending");
        setErrorMsg(null);
      }
      clearCallTimer();
      await stopLocalMedia();
      const measuredDuration = startTimeRef.current
        ? Math.round((Date.now() - startTimeRef.current) / 1000)
        : elapsedSecs;
      pendingCompletionRef.current = {
        durationSeconds: Math.min(MAX_RECORDED_SECONDS, Math.max(0, measuredDuration)),
        completionReason,
      };
      await persistCompletion();
    },
    [clearCallTimer, elapsedSecs, persistCompletion, stopLocalMedia]
  );

  useEffect(() => {
    endCallRef.current = endCall;
  }, [endCall]);

  const startCall = useCallback(async () => {
    if (startInFlightRef.current || turnState !== "idle") return;
    if (!consent) {
      setErrorMsg("Please consent before starting this private career call.");
      return;
    }

    startInFlightRef.current = true;
    isEndingRef.current = false;
    timeLimitTriggeredRef.current = false;
    setTurnState("starting");
    setErrorMsg(null);
    setElapsedSecs(0);

    try {
      const conversationId = await ensureAaryaSession(
        readStoredAaryaSession(),
        storeAaryaSession
      );
      if (!isMountedRef.current) return;
      const careerCall = await startCareerCall({
        conversationId,
        scheduledSessionId,
        consent,
      });
      if (!isMountedRef.current) return;

      conversationIdRef.current = conversationId;
      voiceSessionIdRef.current = careerCall.id;
      const parsedStartedAt = careerCall.started_at
        ? Date.parse(careerCall.started_at)
        : Number.NaN;
      startTimeRef.current = Number.isFinite(parsedStartedAt) ? parsedStartedAt : Date.now();
      const initialElapsed = Math.max(
        0,
        Math.floor((Date.now() - startTimeRef.current) / 1000)
      );
      setElapsedSecs(initialElapsed);

      if (initialElapsed >= CALL_SECONDS) {
        await endCall("time_limit");
        return;
      }

      clearCallTimer();
      timerRef.current = setInterval(() => {
        if (!startTimeRef.current || !isMountedRef.current) return;
        setElapsedSecs(Math.max(0, Math.floor((Date.now() - startTimeRef.current) / 1000)));
      }, 1000);

      const firstName = candidateName?.split(" ")[0] ?? "there";
      const resumed = initialElapsed > 5;
      const greeting = resumed
        ? `Welcome back, ${firstName}. We can continue right where we left off — what would you like me to understand next?`
        : `Hi ${firstName}, this is Aarya — I'm a senior recruiter here at Hireschema. ` +
          `Thanks for hopping on. I've got about fifteen minutes blocked to really understand ` +
          `your background and what you want next, and then I'll line up the roles that genuinely fit. ` +
          `So, to kick us off — tell me a bit about what you're doing right now, and where you'd love to go from here.`;

      setTurnState("aarya_speaking");
      setTranscript("");
      setAaryaText(greeting);
      if (canSpeak) await speak(greeting, "aarya").catch(() => undefined);
      if (!isEndingRef.current && isMountedRef.current) await listenForUser(conversationId);
    } catch (error) {
      if (isMountedRef.current) {
        clearCallTimer();
        setErrorMsg((error as Error).message || "Couldn't connect to Aarya. Please retry.");
        setTurnState("idle");
      }
    } finally {
      startInFlightRef.current = false;
    }
  }, [
    candidateName,
    canSpeak,
    clearCallTimer,
    consent,
    endCall,
    listenForUser,
    scheduledSessionId,
    speak,
    turnState,
  ]);

  useEffect(() => {
    if (
      elapsedSecs >= CALL_SECONDS &&
      voiceSessionIdRef.current &&
      !timeLimitTriggeredRef.current &&
      !isEndingRef.current
    ) {
      timeLimitTriggeredRef.current = true;
      void endCall("time_limit");
    }
  }, [elapsedSecs, endCall]);

  /** Tap mic: barge-in while Aarya speaks, or force-stop capture while listening */
  const handleMicTap = useCallback(async () => {
    if (turnState === "aarya_speaking" || (turnState === "processing" && isPlaying)) {
      stopSpeaking();
      abortRef.current?.abort();
      if (conversationIdRef.current) {
        setTurnState("user_listening");
        await listenForUser(conversationIdRef.current);
      }
      return;
    }
    if (turnState === "user_listening" && isListening) {
      releaseListenWaitRef.current?.();
    }
  }, [turnState, isListening, isPlaying, stopSpeaking, listenForUser]);

  const toggleMute = useCallback(() => {
    const nextMuted = !micMutedRef.current;
    micMutedRef.current = nextMuted;
    setMicMuted(nextMuted);

    if (nextMuted) {
      listeningParkedRef.current = true;
      resumeAfterDiscardRef.current = false;
      if (
        captureCycleInFlightRef.current ||
        recordingStartingRef.current ||
        recordingActiveRef.current ||
        recordingStoppingRef.current
      ) {
        // The recorder owner performs the one stop operation. Marking the
        // capture first guarantees its transcript is discarded after flush.
        discardCaptureRef.current = true;
        releaseListenWaitRef.current?.();
        void stopRecordingOnce();
      }
      return;
    }

    if (turnState !== "user_listening" || !listeningParkedRef.current) return;
    if (
      captureCycleInFlightRef.current ||
      recordingStartingRef.current ||
      recordingActiveRef.current ||
      recordingStoppingRef.current
    ) {
      resumeAfterDiscardRef.current = true;
      return;
    }

    const conversationId = conversationIdRef.current;
    if (!conversationId || isEndingRef.current) return;
    listeningParkedRef.current = false;
    void listenForUser(conversationId);
  }, [listenForUser, stopRecordingOnce, turnState]);

  // Clean up on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      isEndingRef.current = true;
      stopSpeaking();
      abortRef.current?.abort();
      releaseListenWaitRef.current?.();
      void stopRecordingOnce();
      if (timerRef.current) clearInterval(timerRef.current);
      if (listenTimerRef.current) clearTimeout(listenTimerRef.current);
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
    };
  }, [stopRecordingOnce, stopSpeaking]);

  // ── Derived UI state ──────────────────────────────────────────────────────

  const isActive =
    turnState !== "idle" &&
    turnState !== "starting" &&
    turnState !== "done" &&
    turnState !== "ending" &&
    turnState !== "save_failed";
  const isConnecting = turnState === "starting";
  const isDone       = turnState === "done" || turnState === "ending";
  const saveFailed = turnState === "save_failed";
  const formattedTime = `${String(Math.floor(elapsedSecs / 60)).padStart(2, "0")}:${String(elapsedSecs % 60).padStart(2, "0")}`;

  const statusLabel: Record<TurnState, string> = {
    idle:           "Ready to start",
    starting:       "Connecting to Aarya…",
    aarya_speaking: "Aarya is speaking…",
    user_listening: "Your turn — speak now",
    processing:     "Aarya is thinking…",
    ending:         "Saving session…",
    save_failed:    "Saving needs your attention",
    done:           embedded ? "Session complete" : "Session complete — heading to dashboard",
  };
  const visibleStatus =
    isActive && elapsedSecs >= WRAP_WARNING_SECONDS
      ? "Aarya is wrapping up."
      : isActive && micMuted
        ? "Microphone muted."
      : streamStatus ?? statusLabel[turnState];

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
              aria-label={micMuted ? "Unmute microphone and resume listening" : "Mute microphone"}
              aria-pressed={micMuted}
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
              className="w-16 h-16 rounded-full bg-accent text-on-accent flex items-center justify-center shadow-2 hover:bg-accent-hover transition-all"
            >
              <Mic className="h-6 w-6" strokeWidth={1.5} />
            </button>
          )}

          {/* Start button — idle */}
          {turnState === "idle" && (
            <button
              type="button"
              onClick={() => void startCall()}
              className="w-20 h-20 rounded-full bg-accent hover:bg-accent-hover text-on-accent flex items-center justify-center shadow-lg transition-all hover:scale-105 active:scale-95"
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
              onClick={() => void endCall("candidate_ended")}
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

          {saveFailed && (
            <button
              type="button"
              onClick={() => void persistCompletion()}
              className="rounded-full bg-accent px-5 py-3 text-small font-semibold text-on-accent shadow-2 transition-colors hover:bg-accent-hover"
            >
              Retry saving
            </button>
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
              career goals — then start finding you the best matches in your market.
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
