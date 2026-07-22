"use client";

/**
 * useVoice — voice I/O helpers.
 *
 * STT (mic → text): MediaRecorder (browser) → POST /api/v1/voice/stt (Deepgram, server-side)
 * TTS (text → audio): Deepgram Aura → POST /api/v1/voice/tts (server-side),
 *   with the Web Speech API (SpeechSynthesis) as a no-key fallback.
 *
 * Why server-side STT + TTS?
 * Browser SpeechRecognition often fails with `error=network` depending on
 * region/network/browser, and SpeechSynthesis only has whatever voices the OS
 * ships (rarely a natural Indian female). Deepgram is reliable, gives one
 * consistent warm female voice (Aura) everywhere, and keeps keys off the client.
 *
 * Usage:
 *   const { isRecording, isPlaying, startRecording, stopRecording, speak } = useVoice();
 *
 *   await startRecording();                     // starts mic → en-IN
 *   const transcript = await stopRecording();   // stops mic, returns text
 *   await speak("Hello! I found 5 matches.");   // reads text aloud
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiAuthFetch, getAccessToken } from "@/lib/api/auth-fetch";
import { getApiWsBaseUrl } from "@/lib/api/base-url";

// ── Browser Web Speech API (SpeechRecognition) — STT fallback ─────────────────
// Used when the server has no Deepgram key. Requires no API key and runs in the
// browser (Chrome/Edge). Minimal typing — the DOM lib doesn't ship these.

type SpeechRecognitionAlternativeLike = { transcript: string };
type SpeechRecognitionResultLike = ArrayLike<SpeechRecognitionAlternativeLike> & {
  isFinal: boolean;
};
type SpeechRecognitionEventLike = {
  results: ArrayLike<SpeechRecognitionResultLike>;
};
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// ── STT mode resolution (cached for the page session) ─────────────────────────
// Ask the API once whether server-side Deepgram STT is configured. If not (or
// the probe fails), fall back to the browser's Web Speech API so voice still
// works with zero extra keys.

type VoiceMode = "deepgram" | "browser";
type VoiceConfig = { stt: VoiceMode; tts: VoiceMode };
let voiceConfigCache: VoiceConfig | null = null;
let voiceConfigInflight: Promise<VoiceConfig> | null = null;

async function resolveVoiceConfig(): Promise<VoiceConfig> {
  if (voiceConfigCache) return voiceConfigCache;
  if (voiceConfigInflight) return voiceConfigInflight;
  voiceConfigInflight = (async () => {
    const config: VoiceConfig = { stt: "browser", tts: "browser" };
    try {
      const res = await apiAuthFetch("/api/v1/voice/config", { method: "GET" });
      if (res.ok) {
        const j = (await res.json()) as { stt_provider?: string; tts_provider?: string };
        config.stt = j.stt_provider === "deepgram" ? "deepgram" : "browser";
        config.tts = j.tts_provider === "deepgram" ? "deepgram" : "browser";
      }
    } catch {
      // Network/probe failure → browser fallback (no key required).
    }
    voiceConfigCache = config;
    voiceConfigInflight = null;
    return config;
  })();
  return voiceConfigInflight;
}

async function resolveSttMode(): Promise<VoiceMode> {
  return (await resolveVoiceConfig()).stt;
}

export type VoiceSupportStatus = "supported" | "stt_only" | "tts_only" | "unsupported";

/** Returns what voice features are available in this browser. */
export function getVoiceSupportStatus(): VoiceSupportStatus {
  if (typeof window === "undefined") return "unsupported";
  const hasMediaRecorder =
    !!navigator.mediaDevices?.getUserMedia && typeof window.MediaRecorder !== "undefined";
  // STT works via either the MediaRecorder→Deepgram upload path or the native
  // Web Speech API (used as a no-key fallback).
  const hasSTT = hasMediaRecorder || getSpeechRecognitionCtor() !== null;
  const hasTTS = !!window.speechSynthesis;
  if (hasSTT && hasTTS) return "supported";
  if (hasSTT) return "stt_only";
  if (hasTTS) return "tts_only";
  return "unsupported";
}

// ── Speech text cleanup ───────────────────────────────────────────────────────
// The TTS engine literally reads symbols ("asterisk", "smiley face", "hash"),
// which sounds broken. Strip emoji / emoticons / markdown before speaking and
// turn line breaks into natural pauses. (The on-screen transcript keeps the
// original rich text — this only affects what's read aloud.)
function sanitizeForSpeech(text: string): string {
  return (
    text
      // Emoji & pictographs (incl. flags, arrows, dingbats, variation selectors)
      .replace(
        /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2190}-\u{21FF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{1F1E6}-\u{1F1FF}]/gu,
        ""
      )
      // Common ASCII emoticons :) ;) :-D =) etc.
      .replace(/(^|\s)[:;=8][-^]?[)\]([dpDP3]/g, "$1")
      // Markdown links [label](url) → label
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      // Bullet markers at line start
      .replace(/^[ \t]*[-•·*]\s+/gm, "")
      // Numbered list markers at line start ("1. ", "2) ")
      .replace(/^[ \t]*\d+[.)]\s+/gm, "")
      // Emphasis / code / heading / blockquote symbols
      .replace(/[*_`#>~|]/g, "")
      // Paragraph breaks → sentence pause; single breaks → comma pause
      .replace(/\n{2,}/g, ". ")
      .replace(/\n/g, ", ")
      // Tidy spacing around punctuation
      .replace(/\s{2,}/g, " ")
      .replace(/\s+([.,!?])/g, "$1")
      .trim()
  );
}

// Aarya's voice: prefer a natural Indian-English female voice. Names vary by OS
// (macOS "Veena", Windows "Heera"/"Neerja", Chrome/Android "Google English (India)").
const FEMALE_INDIAN_VOICE = /veena|heera|neerja|priya|aditi|raveena|kajal|isha|ananya|swara|lekha/i;
const MALE_VOICE = /rishi|ravi|hemant|prabhat|madhur|kumar/i;
const FEMALE_EN_VOICE = /female|samantha|victoria|karen|tessa|fiona|moira|serena|zira|aria|jenny/i;

function pickAaryaVoice(
  voices: SpeechSynthesisVoice[]
): SpeechSynthesisVoice | null {
  if (!voices.length) return null;
  const indian = voices.filter(
    (v) => /^(en[-_]?in|hi[-_]?in)/i.test(v.lang)
  );
  return (
    // 1. A named female Indian-English voice
    indian.find((v) => FEMALE_INDIAN_VOICE.test(v.name)) ||
    voices.find((v) => FEMALE_INDIAN_VOICE.test(v.name)) ||
    // 2. "Google English (India)" — female on Chrome/Android
    indian.find((v) => /google/i.test(v.name)) ||
    // 3. Any Indian voice that isn't obviously male
    indian.find((v) => !MALE_VOICE.test(v.name)) ||
    indian[0] ||
    // 4. Any female English voice as a last resort
    voices.find((v) => v.lang.startsWith("en") && FEMALE_EN_VOICE.test(v.name)) ||
    voices.find((v) => v.lang.startsWith("en")) ||
    voices[0] ||
    null
  );
}

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [isPlaying, setIsPlaying]     = useState(false);
  const [error, setError]             = useState<string | null>(null);
  // Real-time preview state, updated live while the user speaks.
  //   interimTranscript → words-so-far (browser STT only; Deepgram is batch)
  //   audioLevel        → 0..1 RMS mic loudness, drives the live waveform
  const [interimTranscript, setInterimTranscript] = useState<string>("");
  const [audioLevel, setAudioLevel]               = useState<number>(0);

  // Refs to avoid stale closures
  const recorderRef       = useRef<MediaRecorder | null>(null);
  const streamRef         = useRef<MediaStream | null>(null);
  const chunksRef         = useRef<BlobPart[]>([]);
  const resolveStopRef    = useRef<((text: string) => void) | null>(null);
  const utteranceRef      = useRef<SpeechSynthesisUtterance | null>(null);
  const recognitionRef    = useRef<SpeechRecognitionLike | null>(null);
  // Deepgram Aura TTS playback (server-side voice) — one reused <audio> element.
  const ttsAudioRef       = useRef<HTMLAudioElement | null>(null);
  // Settles the active Deepgram playback promise when playback is cancelled.
  // Without this, clearing an audio element's handlers leaves callers awaiting
  // a Promise that can never resolve.
  const cancelTtsPlaybackRef = useRef<(() => void) | null>(null);
  const voiceMountedRef = useRef(true);
  // Live mic level meter (Web Audio) — gives a real-time waveform on both the
  // Deepgram and browser STT paths.
  const audioCtxRef       = useRef<AudioContext | null>(null);
  const rafRef            = useRef<number | null>(null);
  const meterStreamRef    = useRef<MediaStream | null>(null);
  // Deepgram live streaming (WS proxy) — word-by-word captions for Deepgram.
  const liveWsRef         = useRef<WebSocket | null>(null);
  const captureCtxRef     = useRef<AudioContext | null>(null);
  const processorRef      = useRef<ScriptProcessorNode | null>(null);
  const liveFinalRef      = useRef<string>(""); // accumulated final segments

  // ── Live mic level meter ──────────────────────────────────────────────────

  const stopLevelMeter = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    setAudioLevel(0);
  }, []);

  const startLevelMeter = useCallback((stream: MediaStream) => {
    try {
      const Ctx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);

      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128; // -1..1
          sum += v * v;
        }
        const rms = Math.sqrt(sum / data.length);
        // Scale up so normal speech fills the meter; clamp to 0..1.
        setAudioLevel(Math.min(1, rms * 3.2));
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      // Meter is best-effort — never block recording on it.
    }
  }, []);

  // ── Browser-native STT (Web Speech API) — no-key fallback ─────────────────

  const startBrowserRecognition = useCallback((): void => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      const msg =
        "Voice input needs Chrome or Edge (or a server STT key). Please switch browsers or type instead.";
      setError(msg);
      throw new Error(msg);
    }

    const recognition = new Ctor();
    recognition.lang = "en-IN";
    // interimResults → stream partial words live for the real-time caption.
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    let finalTranscript = "";

    recognition.onresult = (e) => {
      let finalText = "";
      let interimText = "";
      const results = e.results;
      for (let i = 0; i < results.length; i++) {
        const result = results[i];
        const chunk = result[0]?.transcript ?? "";
        if (result.isFinal) finalText += chunk;
        else interimText += chunk;
      }
      finalTranscript = finalText.trim();
      // Live caption = settled words + the in-flight phrase.
      setInterimTranscript(`${finalText} ${interimText}`.trim());
    };

    recognition.onerror = (e) => {
      const msg =
        e.error === "not-allowed" || e.error === "service-not-allowed"
          ? "Microphone permission denied. Please allow microphone access and try again."
          : e.error === "no-speech"
            ? "" // benign — just nothing was said; resolve empty so the loop retries
            : e.error === "network"
              ? "Speech recognition couldn't reach the network. Check your connection or type instead."
              : `Voice input error (${e.error}).`;
      if (msg) setError(msg);
    };

    recognition.onend = () => {
      setIsRecording(false);
      recognitionRef.current = null;
      stopLevelMeter();
      meterStreamRef.current?.getTracks().forEach((t) => t.stop());
      meterStreamRef.current = null;
      resolveStopRef.current?.(finalTranscript);
      resolveStopRef.current = null;
      setInterimTranscript("");
    };

    try {
      recognition.start();
      setIsRecording(true);
      setInterimTranscript("");
      // Best-effort live mic meter — a separate read-only stream so the
      // waveform reacts to the user's actual voice. Never blocks recording.
      void (async () => {
        try {
          const s = await navigator.mediaDevices.getUserMedia({ audio: true });
          meterStreamRef.current = s;
          startLevelMeter(s);
        } catch {
          /* meter unavailable — interim captions still work */
        }
      })();
    } catch (err) {
      recognitionRef.current = null;
      const msg = err instanceof Error ? err.message : "Could not start voice input.";
      setError(msg);
      throw new Error(msg);
    }
  }, [startLevelMeter, stopLevelMeter]);

  // ── Recording (STT) ──────────────────────────────────────────────────────

  /**
   * Deepgram BATCH path: record the whole utterance, upload to /voice/stt once.
   * Used as a fallback when the live WebSocket can't be established.
   */
  const startDeepgramBatch = useCallback(async (): Promise<void> => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      // Drive the live waveform from the actual mic input.
      startLevelMeter(stream);
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      const msg =
        name === "NotAllowedError"
          ? "Microphone permission denied. Please allow microphone access and try again."
          : "Microphone error: could not access your microphone.";
      setError(msg);
      throw new Error(msg);
    }

    const pickMimeType = (): string | undefined => {
      const candidates = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ];
      for (const mt of candidates) {
        if (window.MediaRecorder?.isTypeSupported?.(mt)) return mt;
      }
      return undefined;
    };

    chunksRef.current = [];
    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;

    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
    };

    recorder.onerror = () => {
      // Release mic immediately
      stopLevelMeter();
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      recorderRef.current = null;

      const msg = "Microphone error: recording failed. Please try again.";
      setError(msg);
      setIsRecording(false);
      resolveStopRef.current?.("");
      resolveStopRef.current = null;
    };

    recorder.onstop = async () => {
      setIsRecording(false);
      stopLevelMeter();

      try {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });

        // Always stop tracks (releases mic indicator immediately)
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        recorderRef.current = null;

        const form = new FormData();
        form.append("file", blob, "voice.webm");

        const res = await apiAuthFetch("/api/v1/voice/stt", {
          method: "POST",
          body: form,
        });

        if (!res.ok) {
          let detail = "Voice transcription failed. Please try again.";
          try {
            const j = (await res.json()) as { detail?: string };
            if (j.detail) detail = j.detail;
          } catch {
            // ignore
          }
          setError(detail);
          resolveStopRef.current?.("");
          resolveStopRef.current = null;
          return;
        }

        const data = (await res.json()) as { transcript?: string };
        const transcript = (data.transcript ?? "").trim();
        resolveStopRef.current?.(transcript);
        resolveStopRef.current = null;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Voice transcription failed.";
        setError(msg);
        resolveStopRef.current?.("");
        resolveStopRef.current = null;
      }
    };

    recorder.start();
    setIsRecording(true);
  }, [startLevelMeter, stopLevelMeter]);

  /** Tear down live capture + WS, reset state, resolve any pending stop. */
  const finalizeLive = useCallback(() => {
    const processor = processorRef.current;
    if (processor) {
      try {
        processor.disconnect();
        processor.onaudioprocess = null;
      } catch {
        /* ignore */
      }
      processorRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    const ctx = captureCtxRef.current;
    if (ctx) {
      ctx.close().catch(() => {});
      captureCtxRef.current = null;
    }
    const ws = liveWsRef.current;
    if (ws) {
      try {
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        ws.close();
      } catch {
        /* ignore */
      }
      liveWsRef.current = null;
    }
    setIsRecording(false);
    setAudioLevel(0);
    setInterimTranscript("");
    const text = liveFinalRef.current.trim();
    const resolve = resolveStopRef.current;
    resolveStopRef.current = null;
    resolve?.(text);
  }, []);

  /**
   * Deepgram LIVE path: stream raw linear16 PCM over a WebSocket and receive
   * word-by-word interim + final transcripts. Falls back to the batch path if
   * the socket can't be established.
   */
  const startDeepgramLive = useCallback(async (): Promise<void> => {
    const token = await getAccessToken();
    if (!token) {
      // No session token to authenticate the WS — fall back to batch upload.
      return startDeepgramBatch();
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      const msg =
        name === "NotAllowedError"
          ? "Microphone permission denied. Please allow microphone access and try again."
          : "Microphone error: could not access your microphone.";
      setError(msg);
      throw new Error(msg);
    }

    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctx) {
      // No Web Audio → can't stream PCM; use batch instead.
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      return startDeepgramBatch();
    }
    const ctx = new Ctx();
    captureCtxRef.current = ctx;
    const sampleRate = Math.round(ctx.sampleRate);

    const wsUrl =
      `${getApiWsBaseUrl()}/api/v1/voice/stream` +
      `?token=${encodeURIComponent(token)}&sr=${sampleRate}`;

    liveFinalRef.current = "";

    return await new Promise<void>((resolveStart, rejectStart) => {
      let settled = false;
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl);
      } catch {
        // Constructor threw → batch fallback.
        ctx.close().catch(() => {});
        captureCtxRef.current = null;
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        startDeepgramBatch().then(resolveStart).catch(rejectStart);
        return;
      }
      ws.binaryType = "arraybuffer";
      liveWsRef.current = ws;

      const fallbackToBatch = () => {
        if (settled) return;
        settled = true;
        clearTimeout(openTimer);
        try {
          ws.onopen = null;
          ws.onerror = null;
          ws.onmessage = null;
          ws.onclose = null;
          ws.close();
        } catch {
          /* ignore */
        }
        liveWsRef.current = null;
        ctx.close().catch(() => {});
        captureCtxRef.current = null;
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        startDeepgramBatch().then(resolveStart).catch(rejectStart);
      };

      // If the socket doesn't open quickly, give up on live and use batch.
      const openTimer = setTimeout(fallbackToBatch, 4000);

      ws.onerror = () => {
        // Error before open → fall back; after open → onclose finalizes.
        if (!settled) fallbackToBatch();
      };

      ws.onopen = () => {
        if (settled) return;
        settled = true;
        clearTimeout(openTimer);

        const source = ctx.createMediaStreamSource(stream);
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;
        // Route through a muted gain so onaudioprocess fires without echoing
        // the mic back to the speakers.
        const mute = ctx.createGain();
        mute.gain.value = 0;
        source.connect(processor);
        processor.connect(mute);
        mute.connect(ctx.destination);

        processor.onaudioprocess = (e) => {
          const input = e.inputBuffer.getChannelData(0);
          // Live waveform level (RMS).
          let sum = 0;
          for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
          setAudioLevel(Math.min(1, Math.sqrt(sum / input.length) * 3.2));
          // Float32 [-1,1] → linear16 PCM, then ship to the proxy.
          if (ws.readyState === WebSocket.OPEN) {
            const pcm = new Int16Array(input.length);
            for (let i = 0; i < input.length; i++) {
              const s = Math.max(-1, Math.min(1, input[i]));
              pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
            }
            ws.send(pcm.buffer);
          }
        };

        setInterimTranscript("");
        setIsRecording(true);
        resolveStart();
      };

      ws.onmessage = (ev) => {
        if (typeof ev.data !== "string") return;
        let payload: { transcript?: string; is_final?: boolean; error?: string };
        try {
          payload = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (payload.error) {
          setError(payload.error);
          return;
        }
        const t = payload.transcript;
        if (typeof t === "string" && t) {
          if (payload.is_final) {
            // Settle this segment; future interims build on top of it.
            liveFinalRef.current = `${liveFinalRef.current} ${t}`.trim();
            setInterimTranscript(liveFinalRef.current);
          } else {
            setInterimTranscript(`${liveFinalRef.current} ${t}`.trim());
          }
        }
      };

      ws.onclose = () => {
        // Only finalize if the user has asked to stop (resolveStopRef set).
        // An unexpected mid-recording close keeps whatever we have; the
        // session's stopRecording will then resolve it immediately.
        if (resolveStopRef.current) finalizeLive();
      };
    });
  }, [startDeepgramBatch, finalizeLive]);

  const startRecording = useCallback(async (): Promise<void> => {
    setError(null);
    setInterimTranscript("");

    // Decide STT path: prefer server-side Deepgram when configured (more
    // reliable + live captions), otherwise the browser's Web Speech API.
    const mode = await resolveSttMode();
    if (mode === "browser") {
      startBrowserRecognition();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      // Server STT is configured but this browser can't capture audio — try
      // the native recognizer as a last resort before giving up.
      if (getSpeechRecognitionCtor()) {
        startBrowserRecognition();
        return;
      }
      const msg = "Voice input is not supported in this browser. Please use Chrome or Edge.";
      setError(msg);
      throw new Error(msg);
    }

    // Deepgram configured: stream live for word-by-word captions. The live
    // path falls back to batch upload internally if the socket fails.
    await startDeepgramLive();
  }, [startBrowserRecognition, startDeepgramLive]);

  const stopRecording = useCallback(async (): Promise<string> => {
    return new Promise((resolve) => {
      // Deepgram LIVE path: stop capturing, flush, finalize on close/timeout.
      const liveWs = liveWsRef.current;
      if (liveWs) {
        resolveStopRef.current = resolve;
        // Stop capturing immediately (releases mic, freezes the meter).
        const processor = processorRef.current;
        if (processor) {
          try {
            processor.disconnect();
            processor.onaudioprocess = null;
          } catch {
            /* ignore */
          }
          processorRef.current = null;
        }
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setAudioLevel(0);
        // Ask the server (→ Deepgram) to flush buffered audio into a final.
        try {
          if (liveWs.readyState === WebSocket.OPEN) liveWs.send("CloseStream");
        } catch {
          /* ignore */
        }
        if (liveWs.readyState === WebSocket.CLOSED) {
          finalizeLive();
          return;
        }
        // Finalize when the server closes, or after a short flush window.
        const flushTimer = setTimeout(finalizeLive, 1800);
        liveWs.onclose = () => {
          clearTimeout(flushTimer);
          finalizeLive();
        };
        return;
      }

      // Browser Web Speech API path: stop() fires onend, which resolves.
      const recognition = recognitionRef.current;
      if (recognition) {
        resolveStopRef.current = resolve;
        try {
          recognition.stop();
        } catch {
          recognitionRef.current = null;
          setIsRecording(false);
          resolveStopRef.current = null;
          resolve("");
        }
        return;
      }

      // MediaRecorder → Deepgram path.
      const recorder = recorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        setIsRecording(false);
        resolve("");
        return;
      }
      resolveStopRef.current = resolve;
      recorder.stop();
    });
  }, [finalizeLive]);

  // ── Playback (TTS) ───────────────────────────────────────────────────────

  /**
   * Stop any in-flight speech, browser or server.
   * Defined first so both speak paths can call it before starting.
   */
  // Generation token: speak/speakFiller fetch TTS audio for 1-3s BEFORE an
  // Audio element exists, so cancelSpeech alone can't stop them — two clips
  // fetched in parallel would both start playing (the "two voices at once"
  // bug). Every new request bumps the generation; a clip may only start if
  // its generation is still current.
  const speechGenRef = useRef(0);
  // True while a reply clip is being fetched/played — fillers are decorative
  // and must never talk over the actual reply.
  const speakBusyRef = useRef(false);

  const cancelSpeech = useCallback(() => {
    speechGenRef.current += 1;
    try {
      window.speechSynthesis.cancel();
    } catch {
      /* ignore */
    }
    cancelTtsPlaybackRef.current?.();
  }, []);

  /**
   * Deepgram Aura TTS: fetch synthesized MP3 from the server and play it.
   * One consistent, natural female voice across all devices (vs. whatever
   * voices the OS happens to have for SpeechSynthesis). Throws on any failure
   * so speak() can fall back to the browser voice.
   */
  const speakDeepgram = useCallback(
    async (spoken: string, playbackRate = 1.0, isCurrent?: () => boolean): Promise<void> => {
    const res = await apiAuthFetch("/api/v1/voice/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: spoken }),
    });
    if (!res.ok) throw new Error(`TTS ${res.status}`);
    const blob = await res.blob();
    if (!blob.size) throw new Error("Empty TTS audio");
    // A newer speak/cancel superseded this clip while it was being fetched —
    // drop it instead of playing over the newer one.
    if (isCurrent && !isCurrent()) return;
    const url = URL.createObjectURL(blob);

    await new Promise<void>((resolve, reject) => {
      const audio = new Audio(url);
      audio.playbackRate = playbackRate;
      ttsAudioRef.current = audio;
      let settled = false;
      const settle = (options?: { error?: Error; stopAudio?: boolean }) => {
        if (settled) return;
        settled = true;
        audio.onplay = null;
        audio.onended = null;
        audio.onerror = null;
        if (cancelTtsPlaybackRef.current === cancelPlayback) {
          cancelTtsPlaybackRef.current = null;
        }
        if (ttsAudioRef.current === audio) ttsAudioRef.current = null;
        if (options?.stopAudio) {
          try {
            audio.pause();
            audio.removeAttribute("src");
            audio.load();
          } catch {
            /* The promise still settles even if media teardown fails. */
          }
        }
        URL.revokeObjectURL(url);
        if (voiceMountedRef.current) setIsPlaying(false);
        if (options?.error) reject(options.error);
        else resolve();
      };
      const cancelPlayback = () => settle({ stopAudio: true });
      cancelTtsPlaybackRef.current?.();
      cancelTtsPlaybackRef.current = cancelPlayback;
      audio.onplay = () => {
        if (voiceMountedRef.current) setIsPlaying(true);
      };
      audio.onended = () => settle();
      audio.onerror = () => settle({ error: new Error("TTS playback failed") });
      audio.play().catch((err) => {
        settle({
          error: err instanceof Error ? err : new Error("TTS play() rejected"),
          stopAudio: true,
        });
      });
    });
    },
    []
  );

  const speakBrowser = useCallback(
    async (spoken: string, playbackRate = 1.0, isCurrent?: () => boolean): Promise<void> => {
      window.speechSynthesis.cancel();
      if (isCurrent && !isCurrent()) return;

      return new Promise((resolve) => {
        const utterance = new SpeechSynthesisUtterance(spoken);
        utterance.rate   = Math.min(1.1, 0.98 * playbackRate);
        utterance.pitch  = 1.0;
        utterance.volume = 1.0;

        const applyVoice = () => {
          const v = pickAaryaVoice(window.speechSynthesis.getVoices());
          if (v) {
            utterance.voice = v;
            utterance.lang = v.lang; // match the chosen voice (usually en-IN)
          } else {
            utterance.lang = "en-IN"; // bias the default toward an Indian voice
          }
        };

        applyVoice();
        utteranceRef.current = utterance;

        utterance.onstart = () => setIsPlaying(true);
        utterance.onend   = () => { setIsPlaying(false); resolve(); };
        utterance.onerror = () => { setIsPlaying(false); resolve(); }; // non-fatal

        // Voices may not be loaded on the first call — wait for them once.
        if (window.speechSynthesis.getVoices().length === 0) {
          window.speechSynthesis.onvoiceschanged = () => {
            applyVoice();
            window.speechSynthesis.speak(utterance);
          };
        } else {
          window.speechSynthesis.speak(utterance);
        }
      });
    },
    []
  );

  type SpeakOptions = { hinglish?: boolean };

  const speak = useCallback(
    async (
      text: string,
      _voice: "aarya" | "nitya" = "aarya",
      opts?: SpeakOptions
    ): Promise<void> => {
      const spoken = sanitizeForSpeech(text);
      if (!spoken) return;

      cancelSpeech();
      const gen = speechGenRef.current;
      const isCurrent = () => speechGenRef.current === gen;
      speakBusyRef.current = true;

      try {
        const playbackRate = opts?.hinglish ? 0.9 : 1.0;
        const { tts } = await resolveVoiceConfig();
        if (!isCurrent()) return;
        if (tts === "deepgram") {
          try {
            await speakDeepgram(spoken, playbackRate, isCurrent);
            return;
          } catch {
            /* fall through */
          }
        }
        if (!isCurrent()) return;
        await speakBrowser(spoken, playbackRate, isCurrent);
      } finally {
        if (isCurrent()) speakBusyRef.current = false;
      }
    },
    [cancelSpeech, speakDeepgram, speakBrowser]
  );

  /** Short non-blocking filler clip while tools run (does not await playback). */
  const speakFiller = useCallback(
    (text: string) => {
      const spoken = sanitizeForSpeech(text);
      if (!spoken) return;
      // Fillers are decorative — never interrupt or overlap the actual reply.
      if (speakBusyRef.current) return;
      cancelSpeech();
      const gen = speechGenRef.current;
      const isCurrent = () => speechGenRef.current === gen;
      void (async () => {
        const { tts } = await resolveVoiceConfig();
        if (!isCurrent()) return;
        if (tts === "deepgram") {
          try {
            await speakDeepgram(spoken, 1.0, isCurrent);
            return;
          } catch {
            /* fall through */
          }
        }
        if (!isCurrent()) return;
        await speakBrowser(spoken, 1.0, isCurrent);
      })();
    },
    [cancelSpeech, speakDeepgram, speakBrowser]
  );

  const stopSpeaking = useCallback(() => {
    cancelSpeech();
    setIsPlaying(false);
  }, [cancelSpeech]);

  // Release the mic meter, meter-only stream, and any live streaming socket /
  // audio context if the component unmounts mid-recording (e.g. the user
  // navigates away during a turn).
  useEffect(() => {
    voiceMountedRef.current = true;
    return () => {
      voiceMountedRef.current = false;
      stopLevelMeter();
      meterStreamRef.current?.getTracks().forEach((t) => t.stop());
      meterStreamRef.current = null;
      // Live streaming teardown (no setState — component is unmounting).
      try {
        processorRef.current?.disconnect();
      } catch {
        /* ignore */
      }
      processorRef.current = null;
      captureCtxRef.current?.close().catch(() => {});
      captureCtxRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      try {
        liveWsRef.current?.close();
      } catch {
        /* ignore */
      }
      liveWsRef.current = null;
      // Stop any server-TTS audio playing on unmount.
      cancelTtsPlaybackRef.current?.();
    };
  }, [stopLevelMeter]);

  return {
    isRecording,
    isPlaying,
    error,
    interimTranscript,
    audioLevel,
    startRecording,
    stopRecording,
    speak,
    speakFiller,
    stopSpeaking,
  };
}
