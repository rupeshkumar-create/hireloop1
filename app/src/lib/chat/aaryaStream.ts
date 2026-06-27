/**
 * Unified Aarya chat transport — single SSE client for text chat + voice turns.
 *
 * Both ChatInterface and VoiceSession post to the same endpoint and parse the
 * same event stream. Keeping this in one module prevents drift when the API
 * adds new stream fields (status, errors, partial text).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import type { MatchedJob } from "@/lib/api/matches";

export type AaryaContentType = "text" | "voice";

export type AaryaStatusMeta = {
  spokenFiller?: string;
  etaSec?: number;
  hinglishHint?: boolean;
};

export type AaryaStreamCallbacks = {
  onStatus?: (status: string, meta?: AaryaStatusMeta) => void;
  onText?: (chunk: string, accumulated: string) => void;
  onJobs?: (jobs: MatchedJob[]) => void;
  onError?: (error: string) => void;
};

export type AaryaStreamResult = {
  text: string;
  error: string | null;
  sawDone: boolean;
  jobs: MatchedJob[];
  hinglishHint: boolean;
};

type StreamPayload = {
  text?: string;
  error?: string;
  status?: string;
  spoken_filler?: string;
  eta_sec?: number;
  hinglish_hint?: boolean;
  jobs?: MatchedJob[];
};

export const AARYA_SESSION_STORAGE_KEY = "hireloop_aarya_session_id";
export const VOICE_SEND_ON_PAUSE_KEY = "hireloop_voice_send_on_pause";

export function readStoredAaryaSession(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(AARYA_SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeAaryaSession(id: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(AARYA_SESSION_STORAGE_KEY, id);
  } catch {
    /* ignore quota / private mode */
  }
}

export function readVoiceSendOnPause(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const v = localStorage.getItem(VOICE_SEND_ON_PAUSE_KEY);
    if (v === null) return true;
    return v === "1";
  } catch {
    return true;
  }
}

export function storeVoiceSendOnPause(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(VOICE_SEND_ON_PAUSE_KEY, enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export async function createAaryaSession(): Promise<string> {
  const res = await apiAuthFetch("/api/v1/chat/sessions", { method: "POST" });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    const detail =
      typeof (errBody as { detail?: unknown }).detail === "string"
        ? (errBody as { detail: string }).detail
        : "Could not create chat session";
    throw new Error(detail);
  }
  const data = (await res.json()) as { conversation_id: string };
  return data.conversation_id;
}

/** Ensure a conversation id exists (lazy session creation). */
export async function ensureAaryaSession(
  currentId: string | null,
  onCreated?: (id: string) => void
): Promise<string> {
  if (currentId) return currentId;
  const id = await createAaryaSession();
  onCreated?.(id);
  return id;
}

/** Prefetch profile + top matches before first turn (voice + chat). */
export async function prefetchAaryaWarmup(): Promise<{
  profileCompleteness: number;
  prefetchedJobs: MatchedJob[];
  matchCount: number;
}> {
  const res = await apiAuthFetch("/api/v1/chat/warmup", { cache: "no-store" });
  if (!res.ok) {
    return { profileCompleteness: 0, prefetchedJobs: [], matchCount: 0 };
  }
  const data = (await res.json()) as {
    profile_completeness?: number;
    prefetched_jobs?: MatchedJob[];
    match_count?: number;
  };
  return {
    profileCompleteness: Number(data.profile_completeness) || 0,
    prefetchedJobs: Array.isArray(data.prefetched_jobs) ? data.prefetched_jobs : [],
    matchCount: Number(data.match_count) || 0,
  };
}

/**
 * Stream one user turn to Aarya. Returns the full assistant reply text.
 * Throws on HTTP or stream-level errors.
 */
export async function streamAaryaMessage(
  conversationId: string,
  content: string,
  contentType: AaryaContentType,
  callbacks: AaryaStreamCallbacks = {},
  signal?: AbortSignal
): Promise<AaryaStreamResult> {
  const res = await apiAuthFetch(
    `/api/v1/chat/sessions/${conversationId}/messages`,
    {
      method: "POST",
      headers: {
        "X-Hireloop-Channel": contentType,
      },
      body: JSON.stringify({ content, content_type: contentType }),
      signal,
    }
  );

  if (!res.ok || !res.body) {
    const errBody = await res.json().catch(() => ({}));
    const detail =
      typeof (errBody as { detail?: unknown }).detail === "string"
        ? (errBody as { detail: string }).detail
        : res.ok
          ? "No response stream"
          : `Request failed (${res.status})`;
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let accumulated = "";
  let streamError: string | null = null;
  let sawDone = false;
  let buffer = "";
  let hinglishHint = false;
  const jobs: MatchedJob[] = [];

  const consumeFrames = () => {
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const data = line.slice(5).replace(/^ /, "");

      if (data === "[DONE]") {
        sawDone = true;
        continue;
      }

      try {
        const parsed = JSON.parse(data) as StreamPayload;
        if (parsed.error) {
          streamError = parsed.error;
          callbacks.onError?.(parsed.error);
          continue;
        }
        if (parsed.status) {
          if (parsed.hinglish_hint) hinglishHint = true;
          callbacks.onStatus?.(parsed.status, {
            spokenFiller: parsed.spoken_filler,
            etaSec: parsed.eta_sec,
            hinglishHint: parsed.hinglish_hint,
          });
        }
        if (Array.isArray(parsed.jobs) && parsed.jobs.length > 0) {
          jobs.push(...parsed.jobs);
          callbacks.onJobs?.(parsed.jobs);
        }
        if (parsed.text) {
          accumulated += parsed.text;
          callbacks.onText?.(parsed.text, accumulated);
        }
      } catch {
        // Ignore malformed/partial frames — buffering handles the rest.
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      consumeFrames();
    }
    if (sawDone) break;
    if (done) {
      buffer += decoder.decode(undefined, { stream: false });
      consumeFrames();
      break;
    }
  }

  if (streamError) {
    throw new Error(streamError);
  }

  if (!sawDone && accumulated.length > 0) {
    throw new Error("Stream ended before completion — please try again.");
  }

  return {
    text: accumulated,
    error: null,
    sawDone,
    jobs,
    hinglishHint,
  };
}
