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

export function aaryaSessionStorageKey(userId?: string | null): string {
  return userId ? `${AARYA_SESSION_STORAGE_KEY}_${userId}` : AARYA_SESSION_STORAGE_KEY;
}

export function readStoredAaryaSession(userId?: string | null): string | null {
  if (typeof window === "undefined") return null;
  try {
    const scoped = userId ? localStorage.getItem(aaryaSessionStorageKey(userId)) : null;
    if (scoped) return scoped;
    // Legacy global key — only used when user id is not known yet.
    if (!userId) return localStorage.getItem(AARYA_SESSION_STORAGE_KEY);
    return null;
  } catch {
    return null;
  }
}

export function storeAaryaSession(id: string, userId?: string | null): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(aaryaSessionStorageKey(userId), id);
    if (userId) {
      localStorage.removeItem(AARYA_SESSION_STORAGE_KEY);
    }
  } catch {
    /* ignore quota / private mode */
  }
}

/** Forget the stored conversation id (e.g. after a 404 — it was deleted). */
export function clearAaryaSession(userId?: string | null): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(aaryaSessionStorageKey(userId));
    localStorage.removeItem(AARYA_SESSION_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Thrown when the conversation no longer exists server-side; callers retry. */
export class StaleSessionError extends Error {
  constructor(message = "Conversation not found") {
    super(message);
    this.name = "StaleSessionError";
  }
}

function parseApiErrorDetail(res: Response, body: unknown): string {
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "object" && item && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return String(item);
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (res.status === 404) {
    return "Conversation not found — starting a fresh chat.";
  }
  return `Request failed (${res.status})`;
}

export function sanitizeChatError(message: string): string {
  const lower = (message || "").toLowerCase();
  if (
    lower.includes("402") ||
    lower.includes("requires more credits") ||
    lower.includes("can only afford") ||
    lower.includes("openrouter") ||
    lower.includes("error code:") ||
    lower.includes("{'error'") ||
    lower.includes('"error"') ||
    lower.includes("api key") ||
    lower.includes("unauthorized") ||
    lower.includes("rate limit")
  ) {
    return "Failed.";
  }
  return message || "Failed.";
}

async function openPrimarySession(): Promise<string> {
  const getRes = await apiAuthFetch("/api/v1/chat/sessions/primary", {
    cache: "no-store",
  });
  if (getRes.ok) {
    const data = (await getRes.json()) as { conversation_id: string };
    return data.conversation_id;
  }

  // Older API builds only expose POST /sessions (same behaviour).
  const postRes = await apiAuthFetch("/api/v1/chat/sessions", {
    method: "POST",
    cache: "no-store",
  });
  if (postRes.ok) {
    const data = (await postRes.json()) as { conversation_id: string };
    return data.conversation_id;
  }

  const errBody = await postRes.json().catch(() => ({}));
  throw new Error(parseApiErrorDetail(postRes, errBody));
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

/** Return the user's canonical Supabase-backed Aarya conversation id. */
export async function resolvePrimaryAaryaSession(): Promise<string> {
  return openPrimarySession();
}

export async function createAaryaSession(): Promise<string> {
  return resolvePrimaryAaryaSession();
}

/** Ensure a conversation id exists (lazy session creation). */
export async function ensureAaryaSession(
  currentId: string | null,
  onCreated?: (id: string) => void
): Promise<string> {
  if (currentId) return currentId;
  const id = await resolvePrimaryAaryaSession();
  onCreated?.(id);
  return id;
}

/** Prefetch profile/chat metadata before first turn. Jobs are opt-in. */
export async function prefetchAaryaWarmup(
  options: { includeJobs?: boolean } = {}
): Promise<{
  profileCompleteness: number;
  prefetchedJobs: MatchedJob[];
  matchCount: number;
}> {
  const params = new URLSearchParams();
  if (options.includeJobs) params.set("include_jobs", "true");
  const qs = params.toString();
  const res = await apiAuthFetch(`/api/v1/chat/warmup${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
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

export type AaryaHistoryMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  content_type: "text" | "voice";
  created_at: string;
};

/** Load the full message history for a conversation (paginated server-side). */
export async function fetchAaryaChatHistory(
  conversationId: string
): Promise<AaryaHistoryMessage[]> {
  const out: AaryaHistoryMessage[] = [];
  const pageSize = 100;
  let offset = 0;
  for (;;) {
    const res = await apiAuthFetch(
      `/api/v1/chat/sessions/${conversationId}/messages?limit=${pageSize}&offset=${offset}`,
      { cache: "no-store" }
    );
    if (!res.ok) break;
    const batch = (await res.json()) as AaryaHistoryMessage[];
    if (!Array.isArray(batch) || batch.length === 0) break;
    out.push(...batch);
    if (batch.length < pageSize) break;
    offset += pageSize;
  }
  return out;
}

/** User-wise history on the primary Supabase thread (all messages, day one). */
export async function fetchUserChatHistory(): Promise<{
  conversationId: string;
  messages: AaryaHistoryMessage[];
}> {
  const out: AaryaHistoryMessage[] = [];
  const pageSize = 200;
  let offset = 0;
  let conversationId = "";
  for (;;) {
    const res = await apiAuthFetch(
      `/api/v1/chat/history?limit=${pageSize}&offset=${offset}`,
      { cache: "no-store" }
    );
    if (!res.ok) break;
    const data = (await res.json()) as {
      conversation_id?: string;
      messages?: AaryaHistoryMessage[];
      total?: number;
    };
    if (data.conversation_id) conversationId = data.conversation_id;
    const batch = Array.isArray(data.messages) ? data.messages : [];
    if (!batch.length) break;
    out.push(...batch);
    if (batch.length < pageSize) break;
    offset += pageSize;
  }
  return { conversationId, messages: out };
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
    const detail = parseApiErrorDetail(res, errBody);
    // The stored conversation was deleted (e.g. data reset) — forget it so the
    // caller can create a fresh session and retry instead of dead-ending.
    if (res.status === 404) {
      clearAaryaSession();
      throw new StaleSessionError(detail);
    }
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
    throw new Error(sanitizeChatError(streamError));
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
