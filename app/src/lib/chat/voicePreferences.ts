/** Persisted chat voice / reply preferences (client-only). */

export type ChatReplyMode = "text" | "voice";

export const CHAT_REPLY_MODE_KEY = "hireloop_chat_reply_mode";
export const VOICE_SEND_ON_PAUSE_KEY = "hireloop_voice_send_on_pause";
export const CHAT_COACH_SEEN_KEY = "hireloop_chat_voice_coach_seen";

/** When true, releasing the mic sends immediately (hold-to-send). Default: true. */
export function readSendImmediatelyOnRelease(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const v = localStorage.getItem(VOICE_SEND_ON_PAUSE_KEY);
    if (v === null) return true;
    return v === "1";
  } catch {
    return true;
  }
}

export function storeSendImmediatelyOnRelease(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(VOICE_SEND_ON_PAUSE_KEY, enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
}

/** Review before send = inverse of send immediately on release. */
export function readReviewBeforeSend(): boolean {
  return !readSendImmediatelyOnRelease();
}

export function storeReviewBeforeSend(enabled: boolean): void {
  storeSendImmediatelyOnRelease(!enabled);
}

export function readChatReplyMode(): ChatReplyMode {
  if (typeof window === "undefined") return "voice";
  try {
    return localStorage.getItem(CHAT_REPLY_MODE_KEY) === "text" ? "text" : "voice";
  } catch {
    return "voice";
  }
}

export function storeChatReplyMode(mode: ChatReplyMode): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CHAT_REPLY_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function readChatCoachSeen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem(CHAT_COACH_SEEN_KEY) === "1";
  } catch {
    return true;
  }
}

export function storeChatCoachSeen(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CHAT_COACH_SEEN_KEY, "1");
  } catch {
    /* ignore */
  }
}
