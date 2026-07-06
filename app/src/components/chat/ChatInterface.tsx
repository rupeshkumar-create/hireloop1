"use client";

/**
 * ChatInterface — Aarya chat UI, Jack & Jill-style.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────┐
 *   │                                                     │
 *   │  [Aarya] Message…                                   │
 *   │                                                     │
 *   │          ┌─────────────────────────────────────┐    │
 *   │          │ Option A                          › │    │
 *   │          │ Option B                          › │    │
 *   │          └─────────────────────────────────────┘    │
 *   │          Or, answer in your own words below         │
 *   │                                                     │
 *   │                                  [You] Message      │
 *   │                                                     │
 *   ├─────────────────────────────────────────────────────┤
 *   │  ┌───────────────────────────────────────────────┐  │
 *   │  │ Ask Aarya anything…                           │  │
 *   │  │                                               │  │
 *   │  │ [📎]                              [📞]  [🎙] │  │
 *   │  └───────────────────────────────────────────────┘  │
 *   └─────────────────────────────────────────────────────┘
 *
 * Option cards: Aarya can embed selectable choices using the protocol:
 *   Normal text here.
 *
 *   ---OPTIONS---
 *   Option A
 *   Option B
 *   ---END---
 *
 * "Performed X actions" is shown as a collapsible row in the message
 * timeline whenever the action count increases.
 *
 * Voice (unified with text — same thread, same memory):
 *   - Mic: record → STT → review/edit transcript → send (not auto-send)
 *   - Voice turns appear as normal messages with a mic badge
 *   - TTS plays the reply; "Switch to text" if playback sounds off
 *   - Phone button: opens 15-min deep-dive modal (same thread, same pipeline)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Route,
  BookOpen,
  Briefcase,
  Check,
  ChevronRight,
  Loader2,
  Mic,
  Paperclip,
  PenLine,
  Search,
  Sparkles,
  Send,
  Square,
  Volume2,
} from "@/components/brand/icons";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { firstNameFromDisplayName } from "@/lib/auth/display-name";
import {
  parseJobFiltersFromText,
  type JobCardFilters,
} from "@/lib/chat/jobFilters";
import {
  getChatWarmupSnapshot,
  warmupChatContext,
  type ChatWarmupSnapshot,
} from "@/lib/chat/warmup";
import type { ApplicationKit } from "@/lib/api/applicationKit";
import { ApplicationKitCards } from "./ApplicationKitCards";
import { MessageText } from "./MessageText";
import { dedupeJobs } from "@/lib/chat/dedupeJobs";
import {
  ensureAaryaSession,
  fetchAaryaChatHistory,
  fetchUserChatHistory,
  readStoredAaryaSession,
  resolvePrimaryAaryaSession,
  readVoiceSendOnPause,
  StaleSessionError,
  sanitizeChatError,
  storeAaryaSession,
  streamAaryaMessage,
  type AaryaStreamCallbacks,
} from "@/lib/chat/aaryaStream";
import {
  readChatCoachSeen,
  readChatReplyMode,
  storeChatCoachSeen,
  storeChatReplyMode,
  type ChatReplyMode,
} from "@/lib/chat/voicePreferences";
import {
  extractNewCompleteSentences,
  remainingSpeechTail,
} from "@/lib/chat/sentenceTts";
import { preconnectVoicePipeline } from "@/lib/voice/preconnect";
import { formatStatusWithEta } from "@/lib/chat/voiceStatus";
import { isJobApplicationIntent, isJobSearchIntent } from "@/lib/chat/messageIntent";
import { useAgentActionsRealtime } from "@/lib/hooks/useAgentActionsRealtime";
import { useVoice } from "@/lib/hooks/useVoice";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import type { MatchedJob } from "@/lib/api/matches";
import { fetchMatchFeedCount, invalidateMatchFeedCache } from "@/lib/api/matches";
import {
  fetchMyProfile,
  invalidateProfileCache,
  type MyProfileData,
  type RemotePreference,
} from "@/lib/api/profile";
import { AgentThinkingIndicator } from "./AgentThinkingIndicator";
import { ActivityTimeline, type AgentAction } from "./ActivityTimeline";
import { ProfileCompletionFlow } from "./ProfileCompletionFlow";
import { ChatJobCards } from "./ChatJobCards";
import { ChatShell } from "@/components/chat/shell/ChatShell";
import { VoiceTranscriptReview } from "./VoiceTranscriptReview";
import { VoiceDeepDiveModal } from "./VoiceDeepDiveModal";
import {
  CareerPathOptionCards,
  type CareerPathOption,
} from "@/components/career/CareerPathOptionCards";
import {
  CareerKickoffFlow,
  type KickoffResult,
} from "./CareerKickoffFlow";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  content_type: "text" | "voice";
  created_at: string;
  /** Job cards from a job_search tool call in this turn */
  jobs?: MatchedJob[];
  /** Apply assets from prepare_application_kit in this turn */
  applicationKits?: ApplicationKit[];
  /** Assistant reply was read aloud after a voice turn */
  spoken?: boolean;
}

type SendOptions = {
  contentType?: "text" | "voice";
  speakReply?: boolean;
};

type StreamRecovery = {
  partial: string;
  continuePrompt: string;
};

/** Subset of the /resumes/upload response we actually use client-side. */
type ResumeUploadResponse = {
  resume_id: string;
  parsed: {
    full_name?: string | null;
    current_title?: string | null;
    current_company?: string | null;
    years_experience?: number | null;
    skills?: string[];
    headline?: string | null;
  };
};

/** Parsed message: text + optional option list extracted from ---OPTIONS--- blocks */
type ParsedMessage = {
  text: string;
  options: string[];
};

interface ChatInterfaceProps {
  /**
   * Pass a known conversation ID (returning user) or null / undefined
   * (new user, or session-create failed server-side).
   * When null/undefined the interface is shown immediately and the session
   * is created lazily on the first message send — so we never block render.
   */
  conversationId?: string | null;
  initialMessages?: Message[];
  /** Pre-populate the input (e.g. from ?init= query param) */
  initialInput?: string;
  className?: string;
  /** Called once when a new session is created lazily, so parents can cache the ID. */
  onSessionCreated?: (id: string) => void;
  candidateName?: string;
  /** Open the 15-min voice deep-dive modal on mount (e.g. ?voice=deep). */
  initialVoiceDeepDive?: boolean;
  /** Start the guided career kickoff flow (post-onboarding, ?kickoff=career). */
  initialKickoff?: boolean;
  /**
   * Programmatically inject + auto-send a message (e.g. a quick action or
   * coaching prompt from a side panel). The `nonce` makes repeated identical
   * prompts re-trigger; we only send when the nonce changes.
   */
  injectedMessage?: { text: string; nonce: number } | null;
  savedJobIds?: Set<string>;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  onRequestIntro?: (job: MatchedJob) => void;
}

const CHAT_COLUMN_CLASS = "max-w-2xl mx-auto px-4";
const COMPOSER_TEXT_MAX_H = 80;
const VOICE_FEATURE_ENABLED = process.env.NEXT_PUBLIC_VOICE_ENABLED !== "false";

// ── Option-block parser ───────────────────────────────────────────────────────

const OPTIONS_RE = /\n*---OPTIONS---\n([\s\S]*?)\n---END---\n*/;

function parseMessage(content: string): ParsedMessage {
  const match = OPTIONS_RE.exec(content);
  if (!match) return { text: content.trim(), options: [] };
  const text = content.replace(OPTIONS_RE, "").trim();
  const options = match[1]
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  return { text, options };
}

// ── Main component ────────────────────────────────────────────────────────────

export function ChatInterface({
  conversationId: conversationIdProp,
  initialMessages = [],
  initialInput,
  className,
  onSessionCreated,
  candidateName,
  initialVoiceDeepDive = false,
  initialKickoff = false,
  injectedMessage,
  savedJobIds = new Set(),
  onSavedChange,
  onRequestIntro,
}: ChatInterfaceProps) {
  const [messages, setMessages]       = useState<Message[]>(initialMessages);
  const [kickoffActive, setKickoffActive] = useState(initialKickoff);
  const [input, setInput]             = useState(initialInput ?? "");
  const [isStreaming, setIsStreaming]  = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [actionCount, setActionCount] = useState(0);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [turnActionBaseline, setTurnActionBaseline] = useState(0);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingApplicationKits, setStreamingApplicationKits] = useState<
    ApplicationKit[]
  >([]);
  const [thinkingStatus, setThinkingStatus] = useState<string | null>(null);
  const [warmup, setWarmup] = useState<ChatWarmupSnapshot | null>(
    () => getChatWarmupSnapshot()
  );
  // Tapping the "Profile X% complete" chip opens the in-chat completion flow
  // (call Aarya or fill the gamified form) instead of sending a plain message.
  const [showProfileFlow, setShowProfileFlow] = useState(false);
  const [pendingVoiceTranscript, setPendingVoiceTranscript] = useState<string | null>(
    null
  );
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const [replyMode, setReplyMode] = useState<ChatReplyMode>("voice");
  const [sendImmediately, setSendImmediately] = useState(true);
  const [voiceDeepDiveOpen, setVoiceDeepDiveOpen] = useState(initialVoiceDeepDive);
  const [showCoachMark, setShowCoachMark] = useState(false);
  const [hinglishHint, setHinglishHint] = useState(false);
  const [authUserId, setAuthUserId] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [matchNudge, setMatchNudge] = useState<string | null>(null);
  const historyLoadedForRef = useRef<string | null>(null);
  const [streamRecovery, setStreamRecovery] = useState<StreamRecovery | null>(null);
  const holdActiveRef = useRef(false);
  const streamJobsRef = useRef<MatchedJob[]>([]);
  const spokenStreamRef = useRef("");
  const streamingTtsQueueRef = useRef<Promise<void>>(Promise.resolve());
  const jobsAnnouncedRef = useRef(false);
  const emptySttRetryRef = useRef(false);
  const hinglishActiveRef = useRef(false);
  /** Live reply-mode for stream TTS — updated synchronously on toggle. */
  const voiceRepliesEnabledRef = useRef(true);

  // Session ID: resolved from prop or created lazily on first send.
  // Use a ref so sendMessage always sees the latest value without needing
  // it in the dependency array (avoids stale-closure bugs).
  const sessionIdRef = useRef<string | null>(conversationIdProp ?? null);
  const streamingApplicationKitsRef = useRef<ApplicationKit[]>([]);
  const lastUserTurnRef = useRef<{
    expectJobCards: boolean;
    expectApplicationKits: boolean;
  } | null>(null);
  // Mirror into state only so the action-counter effect re-subscribes when
  // a new session is created.
  const [sessionId, setSessionId] = useState<string | null>(conversationIdProp ?? null);

  // Sync if the parent resolves the prop later (e.g. after a Supabase round-trip).
  useEffect(() => {
    if (conversationIdProp && !sessionIdRef.current) {
      sessionIdRef.current = conversationIdProp;
      setSessionId(conversationIdProp);
    }
  }, [conversationIdProp]);

  const {
    isRecording,
    isPlaying,
    error: voiceError,
    startRecording,
    stopRecording,
    speak,
    speakFiller,
    stopSpeaking,
    interimTranscript,
  } = useVoice();

  const messagesEndRef  = useRef<HTMLDivElement>(null);
  const textareaRef     = useRef<HTMLTextAreaElement>(null);
  const fileInputRef    = useRef<HTMLInputElement>(null);
  const abortRef        = useRef<AbortController | null>(null);

  // ── Effects ────────────────────────────────────────────────────────────

  useEffect(() => {
    setSendImmediately(readVoiceSendOnPause());
    setReplyMode(readChatReplyMode());
    setShowCoachMark(!readChatCoachSeen());
    void createClient()
      .auth.getUser()
      .then(({ data }) => {
        const uid = data.user?.id ?? null;
        setAuthUserId(uid);
        return warmupChatContext().then((snap) => {
          setWarmup(snap);
          if (!sessionIdRef.current) {
            const id =
              conversationIdProp ?? snap.sessionId ?? readStoredAaryaSession(uid);
            if (id) {
              sessionIdRef.current = id;
              setSessionId(id);
              storeAaryaSession(id, uid);
            }
          }
        });
      })
      .catch(() => {});
  }, [conversationIdProp]);

  // Restore full user chat history from Supabase (primary thread, day one).
  useEffect(() => {
    if (historyLoadedForRef.current === "user") return;

    let cancelled = false;
    setHistoryLoading(true);
    void fetchUserChatHistory()
      .then(({ conversationId, messages: rows }) => {
        if (cancelled) return;
        historyLoadedForRef.current = "user";
        if (conversationId && !sessionIdRef.current) {
          sessionIdRef.current = conversationId;
          setSessionId(conversationId);
          storeAaryaSession(conversationId, authUserId);
        }
        const visible = rows.filter((m) => m.role === "user" || m.role === "assistant");
        if (visible.length > 0) {
          setMessages((prev) =>
            prev.length > 0
              ? prev
              : visible.map((m) => ({
                  id: m.id,
                  role: m.role as "user" | "assistant",
                  content: m.content,
                  content_type: (m.content_type === "voice" ? "voice" : "text") as
                    | "text"
                    | "voice",
                  created_at: m.created_at,
                }))
          );
        }
      })
      .catch(() => {
        const sid = sessionId;
        if (!sid || historyLoadedForRef.current) return;
        void fetchAaryaChatHistory(sid)
          .then((rows) => {
            if (cancelled || !rows.length) return;
            historyLoadedForRef.current = sid;
            setMessages(
              rows
                .filter((m) => m.role === "user" || m.role === "assistant")
                .map((m) => ({
                  id: m.id,
                  role: m.role as "user" | "assistant",
                  content: m.content,
                  content_type: (m.content_type === "voice" ? "voice" : "text") as
                    | "text"
                    | "voice",
                  created_at: m.created_at,
                }))
            );
          })
          .catch(() => undefined);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [authUserId, sessionId]);

  // Proactive nudge when background scoring surfaces strong matches.
  useEffect(() => {
    if (messages.length > 0 || historyLoading) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const count = await fetchMatchFeedCount({ min_score: 0.7 });
        if (!cancelled && count >= 3) {
          setMatchNudge(`${count} new matches above 70% — want to see them?`);
        }
      } catch {
        /* scoring may still be running */
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [messages.length, historyLoading]);

  useEffect(() => {
    if (initialVoiceDeepDive) setVoiceDeepDiveOpen(true);
  }, [initialVoiceDeepDive]);

  useEffect(() => {
    voiceRepliesEnabledRef.current = replyMode === "voice";
  }, [replyMode]);

  const interruptSpeech = useCallback(() => {
    stopSpeaking();
    streamingTtsQueueRef.current = Promise.resolve();
    spokenStreamRef.current = "";
  }, [stopSpeaking]);

  const setReplyModeAndPersist = useCallback(
    (mode: ChatReplyMode) => {
      voiceRepliesEnabledRef.current = mode === "voice";
      setReplyMode(mode);
      storeChatReplyMode(mode);
      if (mode === "text") interruptSpeech();
    },
    [interruptSpeech]
  );

  const cancelRecording = useCallback(async () => {
    holdActiveRef.current = false;
    setPendingVoiceTranscript(null);
    if (!isRecording) return;
    try {
      await stopRecording();
    } catch {
      /* ignore */
    }
    setVoiceProcessing(false);
  }, [isRecording, stopRecording]);

  const handleComposerFocus = useCallback(() => {
    interruptSpeech();
    if (isRecording) void cancelRecording();
  }, [cancelRecording, interruptSpeech, isRecording]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, COMPOSER_TEXT_MAX_H) + "px";
  }, [input]);

  useEffect(() => {
    if (initialInput && textareaRef.current) {
      const ta = textareaRef.current;
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const attachJobsToLastAssistant = useCallback((jobs: MatchedJob[]) => {
    const unique = dedupeJobs(jobs);
    if (!unique.length) return;
    setMessages((prev) => {
      let lastIdx = -1;
      for (let i = prev.length - 1; i >= 0; i -= 1) {
        if (prev[i].role === "assistant") {
          lastIdx = i;
          break;
        }
      }
      if (lastIdx === -1) return prev;
      const last = prev[lastIdx];
      if (last.jobs?.length) return prev;

      // Structured job_search results from the API are authoritative — attach
      // without guessing from prose (Aarya often lists matches without "roles found").
      return prev.map((m, i) => (i === lastIdx ? { ...m, jobs: unique } : m));
    });
  }, []);

  const attachApplicationKitsToLastAssistant = useCallback(
    (kits: ApplicationKit[]) => {
    if (!lastUserTurnRef.current?.expectApplicationKits) return;
    if (!kits.length) return;
    for (const kit of kits) {
      if (kit.saved && kit.job?.job_id) {
        onSavedChange?.(kit.job.job_id, true);
      }
    }
    setStreamingApplicationKits(kits);
    streamingApplicationKitsRef.current = kits;
    setMessages((prev) => {
      let lastIdx = -1;
      for (let i = prev.length - 1; i >= 0; i -= 1) {
        if (prev[i].role === "assistant") {
          lastIdx = i;
          break;
        }
      }
      if (lastIdx === -1) return prev;
      const last = prev[lastIdx];
      if (last.applicationKits?.length) return prev;
      return prev.map((m, i) =>
        i === lastIdx ? { ...m, applicationKits: kits } : m
      );
    });
  },
    [onSavedChange]
  );

  // Realtime agent_actions (R7) — instant timeline during streaming.
  useAgentActionsRealtime(sessionId, authUserId, {
    enabled: Boolean(sessionId && authUserId),
    onActions: (live) => setActions(live),
    onTurnCount: (count) => setActionCount(count),
    onJobs: (jobs) => attachJobsToLastAssistant(jobs),
    onApplicationKits: (kits) => attachApplicationKitsToLastAssistant(kits),
  });

  // Fallback poll when Realtime is unavailable or between turns.
  useEffect(() => {
    if (!sessionId) return;
    const poll = async () => {
      try {
        const res = await apiAuthFetch(
          `/api/v1/chat/sessions/${sessionId}/actions`
        );
        if (!res.ok) return;
        const data: {
          count: number;
          turn_count?: number;
          actions?: AgentAction[];
          jobs?: MatchedJob[];
          application_kits?: ApplicationKit[];
        } = await res.json();
        const turnCount = data.turn_count ?? data.count;
        setActionCount(turnCount);
        if (Array.isArray(data.actions)) setActions(data.actions);
        if (Array.isArray(data.jobs) && data.jobs.length > 0) {
          attachJobsToLastAssistant(data.jobs);
        }
        if (Array.isArray(data.application_kits) && data.application_kits.length > 0) {
          attachApplicationKitsToLastAssistant(data.application_kits);
        }
      } catch { /* silent */ }
    };
    const ms = isStreaming ? 4000 : 8000;
    const id = window.setInterval(poll, ms);
    void poll();
    return () => window.clearInterval(id);
  }, [
    sessionId,
    attachJobsToLastAssistant,
    attachApplicationKitsToLastAssistant,
    isStreaming,
  ]);

  // Pull job cards onto the latest assistant turn as soon as streaming ends.
  useEffect(() => {
    if (isStreaming || !sessionId) return;
    const pull = async () => {
      try {
        const res = await apiAuthFetch(
          `/api/v1/chat/sessions/${sessionId}/actions`
        );
        if (!res.ok) return;
        const data: {
          jobs?: MatchedJob[];
          application_kits?: ApplicationKit[];
        } = await res.json();
        if (Array.isArray(data.jobs) && data.jobs.length > 0) {
          attachJobsToLastAssistant(data.jobs);
        }
        if (Array.isArray(data.application_kits) && data.application_kits.length > 0) {
          attachApplicationKitsToLastAssistant(data.application_kits);
        }
      } catch { /* silent */ }
    };
    void pull();
  }, [
    isStreaming,
    sessionId,
    attachJobsToLastAssistant,
    attachApplicationKitsToLastAssistant,
  ]);

  const appendSystemNote = useCallback((content: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "system",
        content,
        content_type: "text",
        created_at: new Date().toISOString(),
      },
    ]);
  }, []);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("hireloop_voice_session_summary");
      if (!raw) return;
      sessionStorage.removeItem("hireloop_voice_session_summary");
      const summary = JSON.parse(raw) as { jobCount?: number };
      if (summary.jobCount && summary.jobCount > 0) {
        appendSystemNote(
          `Your voice call is saved. I dropped ${summary.jobCount} matching roles in this chat — scroll up after my reply.`
        );
      } else {
        appendSystemNote(
          "Your voice call is saved in this thread. Ask me to show your top matches anytime."
        );
      }
    } catch {
      /* ignore */
    }
  }, [appendSystemNote]);

  const handleJobSaved = useCallback(
    (jobId: string, saved: boolean, jobs: MatchedJob[]) => {
      onSavedChange?.(jobId, saved);
      if (!saved) return;
      const job = jobs.find((j) => j.job_id === jobId);
      if (job) {
        appendSystemNote(
          `Saved **${job.title}** at ${job.company_name ?? "this company"}.`
        );
      }
    },
    [onSavedChange, appendSystemNote]
  );

  const handleRequestIntroWithConfirm = useCallback(
    (job: MatchedJob) => {
      onRequestIntro?.(job);
      appendSystemNote(
        `Intro requested for **${job.title}** at ${job.company_name ?? "this company"}.`
      );
    },
    [onRequestIntro, appendSystemNote]
  );

  // ── Send message ────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (text: string, options: SendOptions = {}) => {
      if (!text.trim() || isStreaming) return;

      interruptSpeech();
      if (isRecording) await cancelRecording();

      const contentType = options.contentType ?? "text";
      const shouldSpeakReply =
        options.speakReply ??
        (contentType === "voice" && voiceRepliesEnabledRef.current);

      setPendingVoiceTranscript(null);
      setStreamRecovery(null);
      setHinglishHint(false);
      hinglishActiveRef.current = false;
      spokenStreamRef.current = "";
      streamingTtsQueueRef.current = Promise.resolve();
      jobsAnnouncedRef.current = false;
      setStreamingApplicationKits([]);
      streamingApplicationKitsRef.current = [];
      streamJobsRef.current = [];
      setThinkingStatus("Thinking…");
      const trimmedIntent = text.trim();
      lastUserTurnRef.current = {
        expectJobCards: isJobSearchIntent(trimmedIntent),
        expectApplicationKits: isJobApplicationIntent(trimmedIntent),
      };

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: text.trim(),
        content_type: contentType,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setStreamingContent("");
      setTurnActionBaseline(actionCount);
      setIsStreaming(true);

      abortRef.current = new AbortController();
      let finalReply = "";
      let accumulated = "";
      let streamFinalized = false;
      const trimmed = text.trim();

      const finalize = (jobsForMessage?: MatchedJob[]) => {
        if (streamFinalized || !accumulated) return;
        streamFinalized = true;
        finalReply = accumulated;
        const kitsForMessage =
          streamingApplicationKitsRef.current.length > 0
            ? streamingApplicationKitsRef.current
            : undefined;
        const jobs =
          jobsForMessage && jobsForMessage.length > 0
            ? dedupeJobs(jobsForMessage)
            : streamJobsRef.current.length > 0
              ? dedupeJobs(streamJobsRef.current)
              : undefined;
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: accumulated,
            content_type: "text",
            created_at: new Date().toISOString(),
            applicationKits: kitsForMessage,
            jobs,
          },
        ]);
        setStreamingContent("");
        setStreamingApplicationKits([]);
        streamingApplicationKitsRef.current = [];
      };

      try {
        let currentSessionId = await ensureAaryaSession(
          sessionIdRef.current ?? readStoredAaryaSession(authUserId),
          (id) => {
            sessionIdRef.current = id;
            setSessionId(id);
            storeAaryaSession(id, authUserId);
            onSessionCreated?.(id);
          }
        );

        const streamCallbacks: AaryaStreamCallbacks = {
            onStatus: (status, meta) => {
              setThinkingStatus(formatStatusWithEta(status, meta?.etaSec));
              if (
                contentType === "voice" &&
                voiceRepliesEnabledRef.current &&
                meta?.spokenFiller
              ) {
                speakFiller(meta.spokenFiller);
              }
              if (meta?.hinglishHint) {
                setHinglishHint(true);
                hinglishActiveRef.current = true;
              }
            },
            onJobs: (jobs) => {
              streamJobsRef.current = dedupeJobs([
                ...streamJobsRef.current,
                ...jobs,
              ]);
              attachJobsToLastAssistant(jobs);
              if (
                shouldSpeakReply &&
                !jobsAnnouncedRef.current &&
                jobs.length > 0
              ) {
                jobsAnnouncedRef.current = true;
                const n = streamJobsRef.current.length;
                speakFiller(
                  `I found ${n} strong match${n !== 1 ? "es" : ""} — scroll up to see them.`
                );
              }
            },
            onText: (_chunk, full) => {
              accumulated = full;
              setThinkingStatus(null);
              setStreamingContent(full);
              if (shouldSpeakReply && voiceRepliesEnabledRef.current) {
                const newSentences = extractNewCompleteSentences(
                  spokenStreamRef.current,
                  full
                );
                for (const sentence of newSentences) {
                  spokenStreamRef.current = spokenStreamRef.current
                    ? `${spokenStreamRef.current} ${sentence}`
                    : sentence;
                  streamingTtsQueueRef.current = streamingTtsQueueRef.current.then(
                    () =>
                      speak(sentence, "aarya", {
                        hinglish: hinglishActiveRef.current,
                      })
                  );
                }
              }
            },
        };

        const abortSignal = abortRef.current?.signal;
        const runStream = (sid: string) =>
          streamAaryaMessage(
            sid,
            trimmed,
            contentType,
            streamCallbacks,
            abortSignal
          );

        let streamResult;
        try {
          streamResult = await runStream(currentSessionId);
        } catch (streamErr) {
          // Stored conversation was deleted server-side (e.g. data reset). The
          // stale id is already cleared; create a fresh session and retry once
          // so the user (text or voice) isn't stuck on "Conversation not found".
          if (streamErr instanceof StaleSessionError) {
            currentSessionId = await resolvePrimaryAaryaSession();
            sessionIdRef.current = currentSessionId;
            setSessionId(currentSessionId);
            storeAaryaSession(currentSessionId, authUserId);
            onSessionCreated?.(currentSessionId);
            streamResult = await runStream(currentSessionId);
          } else {
            throw streamErr;
          }
        }

        if (streamResult.hinglishHint) {
          setHinglishHint(true);
          hinglishActiveRef.current = true;
        }
        if (streamResult.jobs.length > 0) {
          streamJobsRef.current = dedupeJobs(streamResult.jobs);
        }

        if (!streamFinalized && accumulated.trim()) {
          finalize(streamResult.jobs);
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          const message =
            err instanceof Error && err.message
              ? sanitizeChatError(err.message)
              : "Failed.";

          if (accumulated.trim() && !streamFinalized) {
            finalize();
            setStreamRecovery({
              partial: accumulated,
              continuePrompt: "Please continue from where you left off.",
            });
          } else if (!streamFinalized) {
            setMessages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                role: "assistant",
                content: message === "Failed." ? "Failed." : `Sorry, I ran into an issue. ${message}`,
                content_type: "text",
                created_at: new Date().toISOString(),
              },
            ]);
            setStreamingContent("");
          }
        }
      } finally {
        setIsStreaming(false);
        setThinkingStatus(null);
        abortRef.current = null;
        void warmupChatContext({ force: true }).then(setWarmup).catch(() => {});
        textareaRef.current?.focus();
        const shouldSpeak =
          shouldSpeakReply &&
          voiceRepliesEnabledRef.current &&
          finalReply.length > 0;
        if (shouldSpeak) {
          setMessages((prev) => {
            if (!prev.length) return prev;
            const last = prev[prev.length - 1];
            if (last.role !== "assistant") return prev;
            return prev.map((m, i) =>
              i === prev.length - 1 ? { ...m, spoken: true } : m
            );
          });
          const tail = remainingSpeechTail(spokenStreamRef.current, finalReply);
          if (tail.trim()) {
            void streamingTtsQueueRef.current.then(() =>
              speak(tail.slice(0, 2000), "aarya", {
                hinglish: hinglishActiveRef.current,
              })
            );
          } else if (!spokenStreamRef.current.trim()) {
            void speak(finalReply.slice(0, 2000), "aarya", {
              hinglish: hinglishActiveRef.current,
            });
          }
        }
      }
    },
    [
      isStreaming,
      isRecording,
      speak,
      speakFiller,
      onSessionCreated,
      actionCount,
      attachJobsToLastAssistant,
      interruptSpeech,
      cancelRecording,
    ]
  );

  const handleJobApply = useCallback(
    (job: MatchedJob) => {
      const company = job.company_name ?? "this company";
      void sendMessage(
        `I want to apply for ${job.title} at ${company}. Prepare my full application kit for job ${job.job_id}.`
      );
    },
    [sendMessage]
  );

  const handleWhyFit = useCallback(
    (job: MatchedJob) => {
      const company = job.company_name ?? "this company";
      void sendMessage(
        `Why is ${job.title} at ${company} a fit for me? Use job id ${job.job_id}.`
      );
    },
    [sendMessage]
  );

  // ── Voice ───────────────────────────────────────────────────────────────

  const finishVoiceCapture = useCallback(
    async (autoSend: boolean) => {
      setVoiceProcessing(true);
      try {
        const transcript = await stopRecording().catch(() => "");
        if (transcript.trim()) {
          emptySttRetryRef.current = false;
          if (autoSend || sendImmediately) {
            void sendMessage(transcript.trim(), { contentType: "voice" });
          } else {
            setPendingVoiceTranscript(transcript.trim());
          }
        } else if (!emptySttRetryRef.current) {
          emptySttRetryRef.current = true;
          appendSystemNote("I didn't catch that — listening again…");
          await startRecording();
        } else {
          emptySttRetryRef.current = false;
          appendSystemNote(
            "I didn't catch that. Tap and hold the mic to try again, or type instead."
          );
        }
      } finally {
        setVoiceProcessing(false);
      }
    },
    [appendSystemNote, sendMessage, sendImmediately, startRecording, stopRecording]
  );

  const handleMicToggle = useCallback(async () => {
    if (!VOICE_FEATURE_ENABLED || !isRecording) return;
    interruptSpeech();
    await cancelRecording();
  }, [cancelRecording, interruptSpeech, isRecording]);

  const handleMicHoldStart = useCallback(async () => {
    if (!VOICE_FEATURE_ENABLED || isStreaming || voiceProcessing) return;
    holdActiveRef.current = true;
    interruptSpeech();
    setPendingVoiceTranscript(null);
    await startRecording();
  }, [interruptSpeech, isStreaming, startRecording, voiceProcessing]);

  const handleMicHoldEnd = useCallback(async () => {
    if (!holdActiveRef.current) return;
    holdActiveRef.current = false;
    if (!isRecording) return;
    await finishVoiceCapture(sendImmediately);
  }, [finishVoiceCapture, isRecording, sendImmediately]);

  const sendVoiceTranscript = useCallback(() => {
    if (!pendingVoiceTranscript?.trim()) return;
    void sendMessage(pendingVoiceTranscript, { contentType: "voice" });
  }, [pendingVoiceTranscript, sendMessage]);

  // ── Injected messages (from side panels: quick actions / coaching) ────────
  const lastInjectedNonce = useRef<number | null>(null);
  useEffect(() => {
    if (!injectedMessage) return;
    if (injectedMessage.nonce === lastInjectedNonce.current) return;
    lastInjectedNonce.current = injectedMessage.nonce;
    void sendMessage(injectedMessage.text);
  }, [injectedMessage, sendMessage]);

  // ── Resume upload ────────────────────────────────────────────────────────

  const handleResumeUpload = useCallback(
    async (file: File) => {
      if (isUploading || isStreaming) return;

      const ALLOWED = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ];
      if (!ALLOWED.includes(file.type)) {
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant" as const,
            content: "Please upload a PDF or DOCX file.",
            content_type: "text" as const,
            created_at: new Date().toISOString(),
          },
        ]);
        return;
      }

      setIsUploading(true);

      // Show file card in the thread immediately
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "user" as const,
          content: `📎 ${file.name}`,
          content_type: "text" as const,
          created_at: new Date().toISOString(),
        },
      ]);

      try {
        // ── Upload ─────────────────────────────────────────────────────────
        const formData = new FormData();
        formData.append("file", file);

        const uploadRes = await apiAuthFetch("/api/v1/resumes/upload", {
          method: "POST",
          body: formData,
        });

        if (!uploadRes.ok) {
          const errBody = await uploadRes.json().catch(() => ({ detail: uploadRes.statusText }));
          throw new Error((errBody as { detail?: string }).detail ?? "Upload failed");
        }

        const data: ResumeUploadResponse = await uploadRes.json();

        // ── Auto-apply to profile (non-fatal) ──────────────────────────────
        // replace: a CV uploaded in chat is deliberate — the profile follows it.
        try {
          await apiAuthFetch(
            `/api/v1/resumes/${data.resume_id}/apply-to-profile?mode=replace`,
            { method: "POST" },
          );
          invalidateProfileCache();
          invalidateMatchFeedCache();
        } catch {
          // best-effort — don't block the chat message
        }

        // ── Build summary for Aarya ────────────────────────────────────────
        const p = data.parsed;
        const parts: string[] = [];
        if (p.full_name)         parts.push(`Name: ${p.full_name}`);
        if (p.current_title)     parts.push(`Role: ${p.current_title}`);
        if (p.current_company)   parts.push(`Company: ${p.current_company}`);
        if (p.years_experience)  parts.push(`${p.years_experience} years of experience`);
        if (p.skills?.length) {
          const top = p.skills.slice(0, 8).join(", ");
          const extra = p.skills.length > 8 ? ` (+${p.skills.length - 8} more)` : "";
          parts.push(`Skills: ${top}${extra}`);
        }

        const summary = parts.length > 0
          ? `I just uploaded my resume (${file.name}). Here's what was extracted and applied to my profile: ${parts.join("; ")}. What should I do next?`
          : `I just uploaded my resume (${file.name}). What should I do next?`;

        setIsUploading(false);
        await sendMessage(summary);

      } catch (err) {
        setIsUploading(false);
        const msg = err instanceof Error ? err.message : "Unknown error";
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant" as const,
            content: `I wasn't able to process that file. ${msg}. Please try again with a PDF or DOCX under 10 MB.`,
            content_type: "text" as const,
            created_at: new Date().toISOString(),
          },
        ]);
      } finally {
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [isUploading, isStreaming, sendMessage]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage(input);
    }
  };

  // ── Career kickoff (post-onboarding guided flow) ────────────────────────

  const handleKickoffComplete = useCallback((result: KickoffResult) => {
    setKickoffActive(false);
    const content =
      result.jobs.length > 0
        ? `Here are the top **${result.preferredTitle}** roles I found for you. ` +
          "Use Save, Request intro, or Apply on any card — and I'm generating a " +
          "tailored resume for each of your career paths in the background."
        : `Your career paths are saved and I'm pulling fresh **${result.preferredTitle}** ` +
          "openings right now — they'll appear in your Jobs panel in a few minutes. " +
          "Meanwhile, ask me anything about your career.";
    setMessages((prev) => [
      ...prev,
      {
        id: `kickoff-${Date.now()}`,
        role: "assistant",
        content,
        content_type: "text",
        created_at: new Date().toISOString(),
        jobs: result.jobs,
      },
    ]);
  }, []);

  // ── Render ──────────────────────────────────────────────────────────────

  const isEmpty = messages.length === 0 && !streamingContent && !historyLoading;
  const showKickoff = kickoffActive && isEmpty;

  const scrollDeps = useMemo(
    () => [
      messages.length,
      streamingContent,
      pendingVoiceTranscript,
      actionCount,
      isStreaming,
      isUploading,
      streamRecovery,
      showProfileFlow,
    ],
    [
      messages.length,
      streamingContent,
      pendingVoiceTranscript,
      actionCount,
      isStreaming,
      isUploading,
      streamRecovery,
      showProfileFlow,
    ],
  );

  const messagesSlot = (
    <div className={cn(CHAT_COLUMN_CLASS, "py-8 space-y-6")}>
      {showKickoff ? (
        <CareerKickoffFlow
          onComplete={handleKickoffComplete}
          onSkip={() => setKickoffActive(false)}
        />
      ) : isEmpty ? (
        <EmptyState
          onPick={(p) => void sendMessage(p)}
          onUploadResume={() => fileInputRef.current?.click()}
          matchNudge={matchNudge}
          onMatchNudge={() =>
            void sendMessage(
              "Show me my top matches above 70% fit, ranked best first.",
            )
          }
        />
      ) : (
        <>
          {messages.map((msg, i) => {
            const prevUser =
              msg.role === "assistant"
                ? [...messages]
                    .slice(0, i)
                    .reverse()
                    .find((m) => m.role === "user")
                : null;
            const jobFilters = prevUser
              ? parseJobFiltersFromText(prevUser.content)
              : {};
            const msgJobs = msg.role === "assistant" ? (msg.jobs ?? []) : [];
            const msgKits =
              msg.role === "assistant" ? (msg.applicationKits ?? []) : [];

            return (
              <MessageBubble
                key={msg.id}
                message={msg}
                onOptionSelect={(opt) => void sendMessage(opt)}
                actionCount={
                  msg.role === "assistant" &&
                  i === messages.length - 1 &&
                  actionCount > 0
                    ? actionCount
                    : 0
                }
                actions={
                  msg.role === "assistant" && i === messages.length - 1
                    ? actions
                    : []
                }
                jobs={msgJobs}
                applicationKits={msgKits}
                jobFilters={jobFilters}
                conversationId={sessionId ?? undefined}
                savedJobIds={savedJobIds}
                onSavedChange={(jobId, saved) =>
                  handleJobSaved(jobId, saved, msgJobs)
                }
                onRequestIntro={handleRequestIntroWithConfirm}
                onApply={handleJobApply}
                onWhyFit={handleWhyFit}
              />
            );
          })}

          {streamingContent && (
            <MessageBubble
              message={{
                id: "streaming",
                role: "assistant",
                content: streamingContent,
                content_type: "text",
                created_at: new Date().toISOString(),
              }}
              onOptionSelect={() => undefined}
              isStreaming
              actionCount={0}
              actions={[]}
              jobs={[]}
              conversationId={sessionId ?? undefined}
              savedJobIds={savedJobIds}
              onSavedChange={(jobId, saved) => handleJobSaved(jobId, saved, [])}
              onRequestIntro={handleRequestIntroWithConfirm}
              onApply={handleJobApply}
            />
          )}

          {streamRecovery && !isStreaming && (
            <div className="rounded-xl border border-ink-200 bg-paper-1 px-4 py-3 space-y-2 w-full">
              <p className="text-small text-ink-600">
                Connection dropped — your partial reply is saved above.
              </p>
              <button
                type="button"
                onClick={() => void sendMessage(streamRecovery.continuePrompt)}
                className="text-small font-medium text-ink-900 underline underline-offset-2 hover:text-accent"
              >
                Continue
              </button>
            </div>
          )}

          {isUploading && <AgentThinkingIndicator variant="processing" />}

          {isStreaming && !streamingContent && !isUploading && (
            <AgentThinkingIndicator
              actions={actions}
              actionBaseline={turnActionBaseline}
              actionCount={actionCount}
              label={thinkingStatus ?? undefined}
            />
          )}

          {isStreaming && streamingApplicationKits.length > 0 && (
            <ApplicationKitCards kits={streamingApplicationKits} />
          )}
        </>
      )}

      {showProfileFlow && (
        <ProfileCompletionFlow
          profile={warmup?.profile ?? null}
          completeness={warmup?.profileCompleteness ?? null}
          onClose={() => setShowProfileFlow(false)}
          onSaved={() => {
            void warmupChatContext({ force: true })
              .then(setWarmup)
              .catch(() => {});
          }}
        />
      )}
    </div>
  );

  const composerSlot = (
    <div className="bg-paper-0 pt-2 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
      <div className={cn(CHAT_COLUMN_CLASS, "space-y-2")}>
        {showCoachMark && (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-accent/25 bg-accent/5 px-3 py-2.5">
            <p className="text-micro text-ink-700 leading-relaxed">
              Type or hold the mic to talk with Aarya. Your job matches are
              always in <span className="font-medium">Matches</span> on the
              left; chat never blocks them.
            </p>
            <button
              type="button"
              onClick={() => {
                storeChatCoachSeen();
                setShowCoachMark(false);
              }}
              className="shrink-0 text-micro font-medium text-ink-600 hover:text-ink-900"
            >
              Got it
            </button>
          </div>
        )}

        {(isRecording || voiceProcessing || isPlaying || pendingVoiceTranscript) && (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-ink-100 bg-ink-50/80 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="text-micro font-medium text-ink-800">
                {isRecording
                  ? "Listening — release mic to send, or tap below to type"
                  : voiceProcessing
                    ? "Processing voice…"
                    : isPlaying
                      ? "Speaking…"
                      : "Review your message"}
              </p>
              {isRecording && interimTranscript && (
                <p className="text-micro text-ink-600 truncate mt-0.5">
                  {interimTranscript}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {isPlaying && (
                <button
                  type="button"
                  onClick={interruptSpeech}
                  className="text-micro text-ink-600 underline underline-offset-2"
                >
                  Stop
                </button>
              )}
              {isRecording && (
                <button
                  type="button"
                  onClick={() => void handleMicToggle()}
                  className="text-micro text-ink-700 underline underline-offset-2"
                >
                  Cancel
                </button>
              )}
              {replyMode === "voice" && (isPlaying || isRecording) && (
                <button
                  type="button"
                  onClick={() => setReplyModeAndPersist("text")}
                  className="text-micro text-ink-600 underline underline-offset-2"
                >
                  Text replies
                </button>
              )}
            </div>
          </div>
        )}

        {pendingVoiceTranscript && (
          <VoiceTranscriptReview
            transcript={pendingVoiceTranscript}
            onChange={setPendingVoiceTranscript}
            onSend={sendVoiceTranscript}
            onDiscard={() => setPendingVoiceTranscript(null)}
          />
        )}

        <div
          className={cn(
            "bg-paper-1 rounded-lg border border-ink-200 shadow-1",
            "transition-shadow duration-fast",
            "focus-within:shadow-2 focus-within:border-ink-300",
          )}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              if (isPlaying) interruptSpeech();
              if (isRecording) void cancelRecording();
              setInput(e.target.value);
            }}
            onFocus={handleComposerFocus}
            onKeyDown={handleKeyDown}
            placeholder={
              isRecording
                ? "Tap here to type instead…"
                : pendingVoiceTranscript
                  ? "Edit your voice message above, then send."
                  : "Ask Aarya anything…"
            }
            rows={1}
            disabled={
              isStreaming || voiceProcessing || Boolean(pendingVoiceTranscript)
            }
            className={cn(
              "w-full bg-transparent resize-none text-body text-ink-900",
              "placeholder:text-ink-400 focus:outline-none leading-relaxed",
              "px-4 pt-2 pb-1 max-h-[80px] disabled:opacity-60",
            )}
          />

          <div className="flex items-center justify-between px-3 pb-2 pt-0.5">
            <button
              type="button"
              title={isUploading ? "Uploading resume…" : "Upload resume (PDF or DOCX)"}
              disabled={isUploading || isStreaming}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                isUploading || isStreaming
                  ? "text-ink-300 cursor-not-allowed"
                  : "text-ink-400 hover:text-ink-900 hover:bg-ink-50",
              )}
            >
              {isUploading ? (
                <Loader2 className="h-[18px] w-[18px] animate-spin" strokeWidth={1.5} />
              ) : (
                <Paperclip className="h-[18px] w-[18px]" strokeWidth={1.5} />
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleResumeUpload(file);
              }}
            />

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setReplyModeAndPersist("text");
                  textareaRef.current?.focus();
                }}
                aria-label="Type a message"
                title="Type a message"
                className="w-8 h-8 rounded-lg text-ink-400 hover:text-ink-900 hover:bg-ink-50 flex items-center justify-center transition-colors"
              >
                <PenLine className="h-4 w-4" strokeWidth={1.5} />
              </button>

              {input.trim() && (
                <button
                  type="button"
                  onClick={() => void sendMessage(input)}
                  disabled={isStreaming}
                  aria-label="Send message"
                  className={cn(
                    "w-9 h-9 rounded-full flex items-center justify-center transition-colors",
                    !isStreaming
                      ? "bg-accent text-on-accent hover:bg-accent-hover"
                      : "bg-ink-100 text-ink-300 cursor-not-allowed",
                  )}
                >
                  {isStreaming ? (
                    <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
                  ) : (
                    <Send className="h-4 w-4" strokeWidth={1.5} />
                  )}
                </button>
              )}

              {VOICE_FEATURE_ENABLED ? (
                <button
                  type="button"
                  onPointerEnter={() => void preconnectVoicePipeline()}
                  onFocus={() => void preconnectVoicePipeline()}
                  onPointerDown={(e) => {
                    if (e.pointerType === "mouse" && e.button !== 0) return;
                    e.currentTarget.setPointerCapture(e.pointerId);
                    setReplyModeAndPersist("voice");
                    void handleMicHoldStart();
                  }}
                  onPointerUp={(e) => {
                    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
                      e.currentTarget.releasePointerCapture(e.pointerId);
                    }
                    void handleMicHoldEnd();
                  }}
                  onPointerCancel={(e) => {
                    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
                      e.currentTarget.releasePointerCapture(e.pointerId);
                    }
                    void cancelRecording();
                  }}
                  disabled={
                    isStreaming ||
                    voiceProcessing ||
                    Boolean(pendingVoiceTranscript)
                  }
                  aria-pressed={isRecording}
                  aria-label="Hold to talk"
                  title="Hold to talk, release to send"
                  className={cn(
                    "w-10 h-10 rounded-full flex items-center justify-center transition-colors duration-fast",
                    isRecording
                      ? "bg-destructive text-paper-0 animate-pulse"
                      : "bg-ink-50 text-ink-900 border border-ink-100 hover:bg-ink-100 hover:border-ink-200",
                    (isStreaming || voiceProcessing) &&
                      "opacity-40 cursor-not-allowed",
                  )}
                >
                  {isRecording ? (
                    <Square className="h-3.5 w-3.5" strokeWidth={2} fill="currentColor" />
                  ) : (
                    <Mic className="h-[17px] w-[17px]" strokeWidth={2} />
                  )}
                </button>
              ) : (
                !input.trim() && (
                  <button
                    type="button"
                    onClick={() => void sendMessage(input)}
                    disabled={isStreaming}
                    aria-label="Send"
                    className="w-10 h-10 rounded-full bg-ink-100 text-ink-300 flex items-center justify-center"
                  >
                    <Send className="h-4 w-4" strokeWidth={1.5} />
                  </button>
                )
              )}
            </div>
          </div>
        </div>

        {hinglishHint && (
          <p className="text-micro text-ink-500 text-center px-2">
            Hindi/English mix detected —{" "}
            <button
              type="button"
              className="underline underline-offset-2 hover:text-ink-800"
              onClick={() => setReplyModeAndPersist("text")}
            >
              use text replies
            </button>{" "}
            if voice is unclear.
          </p>
        )}

        {voiceError && (
          <div className="text-center space-y-1">
            <p className="text-small text-ink-700">{voiceError}</p>
            <p className="text-micro text-ink-500">
              You can keep typing. Allow microphone access and reload to use voice.
            </p>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <>
      <ChatShell
        className={className}
        messagesSlot={messagesSlot}
        composerSlot={composerSlot}
        messagesEndRef={messagesEndRef}
        scrollDeps={scrollDeps}
      />

      <VoiceDeepDiveModal
        open={voiceDeepDiveOpen}
        onClose={() => setVoiceDeepDiveOpen(false)}
        candidateName={candidateName}
      />
    </>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────
//
// Compact line-wise option rows (checkbox-style) — locked vs unlocked sets differ.

type ActionCardDef = {
  Icon: React.ElementType;
  title: string;
  description: string;
  primary?: boolean;
  /** upload → resume flow; career_paths → path picker; message → sends text */
  kind: "upload" | "message" | "career_paths";
  message?: string;
};

const REMOTE_PREF_PHRASE: Record<RemotePreference, string> = {
  any: "",
  remote_only: " Only show remote roles.",
  onsite_only: " Only show on-site roles.",
};

/**
 * Build a concrete, profile-grounded "Find jobs" prompt so Aarya's semantic
 * search embeds the candidate's *actual* target — role, seniority, location,
 * top skills, and remote preference — instead of a generic phrase. A specific
 * query produces a far better pgvector match than "find me jobs".
 *
 * Returns a sensible generic fallback when the profile hasn't loaded yet or is
 * too sparse to personalise.
 */
function buildFindJobsMessage(profile: MyProfileData | null): string {
  const c = profile?.candidate;
  const generic =
    "Find the best job matches for me based on my profile, skills, and salary expectations";
  if (!c) return generic;

  const role = c.current_title?.trim();
  const city = c.location_city?.trim();
  const skills = (c.skills ?? [])
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 5);
  const years = c.years_experience;
  const lookingFor = c.looking_for?.trim();
  const remote = REMOTE_PREF_PHRASE[c.remote_preference ?? "any"];

  // Need at least a role or some skills to personalise meaningfully.
  if (!role && skills.length === 0 && !lookingFor) return generic;

  const target = lookingFor || role || "roles that fit my background";
  const parts: string[] = [`Find ${target}`];
  if (city) parts.push(`in ${city}`);
  if (typeof years === "number" && years > 0) {
    parts.push(`for someone with ${years}+ years of experience`);
  }
  if (skills.length > 0) parts.push(`matching my skills in ${skills.join(", ")}`);

  return `${parts.join(" ")}.${remote}`.trim();
}

/**
 * Opening options shown first in the chat — "what brings you here?". These are
 * the candidate goals that used to live in onboarding; surfacing them here makes
 * the goal the first thing Aarya asks, and each chip seeds the right prompt.
 */
function buildSmartStarterCards(
  findJobsMessage: string,
  includeCareerPaths: boolean,
): ActionCardDef[] {
  const cards: ActionCardDef[] = [
    {
      Icon: Search,
      title: "Find a new role",
      description: "Your top-ranked matches, best first",
      kind: "message",
      message: findJobsMessage,
      primary: true,
    },
    includeCareerPaths
      ? {
          Icon: Route,
          title: "View top 3 career paths",
          description: "Pick a direction, then see matching roles",
          kind: "career_paths",
        }
      : {
          Icon: BookOpen,
          title: "Improve my resume",
          description: "Tailored fixes before you apply",
          kind: "message",
          message:
            "Review my resume and profile and tell me the most impactful improvements to rank higher in matches.",
        },
    {
      Icon: Briefcase,
      title: "Discuss a job I saw",
      description: "Paste a role and I'll score your fit",
      kind: "message",
      message:
        "I saw a job I'm interested in. Help me evaluate how well it fits my profile.",
    },
  ];
  return cards;
}

function EmptyState({
  onPick,
  onUploadResume,
  matchNudge,
  onMatchNudge,
}: {
  onPick: (text: string) => void;
  onUploadResume: () => void;
  matchNudge?: string | null;
  onMatchNudge?: () => void;
}) {
  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [showPathPicker, setShowPathPicker] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetchMyProfile()
      .then((p) => {
        if (!cancelled) setProfile(p);
      })
      .catch(() => {
        /* fall back to the generic prompt */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const firstName = firstNameFromDisplayName(profile?.user?.full_name ?? undefined) ?? "there";
  const c = profile?.candidate;
  const lookingFor = c?.looking_for?.trim();
  const city = c?.location_city?.trim();
  const intentGreeting =
    lookingFor && city
      ? `You're looking for ${lookingFor} in ${city}. Want me to pull your top matches?`
      : lookingFor
        ? `You're looking for ${lookingFor}. Want me to pull your top matches?`
        : null;
  const greeting =
    intentGreeting ??
    `Hi ${firstName}, I'm Aarya — your AI recruiter. What brings you here today?`;

  const findJobsMessage = buildFindJobsMessage(profile);

  // Meaningful pre-selection: at low profile completeness the highest-value next
  // step is closing profile gaps (better matches downstream), not browsing yet.
  const profileSparse =
    !c ||
    c.profile_complete === false ||
    !c.current_title?.trim() ||
    (c.skills ?? []).filter((s) => s.trim()).length < 3;

  const cards: ActionCardDef[] = buildSmartStarterCards(findJobsMessage, !profileSparse);
  if (intentGreeting && cards[0]?.kind === "message") {
    cards[0] = {
      ...cards[0],
      title: "Show my top matches",
      description: "Ranked by fit to your profile",
      primary: true,
    };
  }

  const handlePathSelect = (opt: CareerPathOption) => {
    onPick(
      `I want to prioritize the "${opt.title}" career path. Show me matching jobs for this direction.`
    );
  };

  return (
    <div className="flex flex-col items-center justify-center text-center pt-6 pb-4 space-y-4 animate-fade-in w-full max-w-md mx-auto">
      <div className="flex flex-col items-center gap-1.5">
        <div className="w-12 h-12 rounded-full bg-ink-900 flex items-center justify-center">
          <Sparkles className="h-5 w-5 text-paper-0" strokeWidth={1.5} />
        </div>
        <p className="text-small font-semibold text-ink-900">
          Aarya <span className="font-normal text-ink-500">· your AI recruiter</span>
        </p>
      </div>

      <div className="space-y-1">
        <p className="text-body text-ink-800 leading-relaxed">{greeting}</p>
        {matchNudge && onMatchNudge && (
          <button
            type="button"
            onClick={onMatchNudge}
            className="mt-2 rounded-full border border-accent bg-accent/5 px-4 py-2 text-small text-ink-900 hover:bg-accent/10 transition-colors"
          >
            {matchNudge}
          </button>
        )}
        <p className="text-small text-ink-400 leading-relaxed">
          Tap a suggestion, or just tell me what you&apos;re looking for.
        </p>
      </div>

      {!showPathPicker ? (
        <div
          className="w-full space-y-1.5 text-left"
          role="group"
          aria-label="Quick actions"
        >
          {cards.map((card) => (
            <button
              key={card.title}
              type="button"
              onClick={() => {
                if (card.kind === "upload") {
                  onUploadResume();
                } else if (card.kind === "career_paths") {
                  setShowPathPicker(true);
                } else if (card.message) {
                  onPick(card.message);
                }
              }}
            className={cn(
              "w-full flex items-center gap-2.5 rounded-lg border px-3 py-2",
              "bg-paper-1 transition-colors duration-fast",
              "hover:bg-ink-50 hover:border-ink-300",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-900 focus-visible:ring-offset-2",
              card.primary
                ? "border-ink-900 ring-1 ring-ink-900/10"
                : "border-ink-200"
            )}
          >
            <span
              className={cn(
                "flex h-4 w-4 shrink-0 items-center justify-center rounded border-2",
                card.primary
                  ? "border-ink-900 bg-ink-900 text-paper-0"
                  : "border-ink-300 bg-paper-0"
              )}
              aria-hidden
            >
              {card.primary && <Check className="h-3 w-3" strokeWidth={3} />}
            </span>
            <card.Icon
              className="h-4 w-4 shrink-0 text-ink-500"
              strokeWidth={1.5}
            />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className="text-small font-medium text-ink-900 leading-snug">
                  {card.title}
                </span>
                {card.primary && (
                  <span className="text-micro font-medium uppercase tracking-wide text-accent">
                    Recommended
                  </span>
                )}
              </span>
              <span className="block text-micro text-ink-500 leading-snug truncate">
                {card.description}
              </span>
            </span>
          </button>
        ))}
        </div>
      ) : (
        <div className="w-full text-left space-y-2">
          <CareerPathOptionCards
            compact
            onSelectPath={handlePathSelect}
          />
          <button
            type="button"
            onClick={() => setShowPathPicker(false)}
            className="text-micro text-ink-500 hover:text-ink-900 transition-colors"
          >
            ← Back to suggestions
          </button>
        </div>
      )}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function stripMarkdownTables(text: string): string {
  const lines = text.split("\n");
  const filtered = lines.filter((line) => {
    const t = line.trim();
    if (t.startsWith("|") && t.endsWith("|")) return false;
    if (/^\|?[\s:-]+\|/.test(t)) return false;
    return true;
  });
  return filtered.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** Drop numbered job blurbs once we render structured JobCards beneath. */
function stripJobListFromText(text: string): string {
  const looksLikeJobLine = (t: string): boolean => {
    if (!/^\d+\.\s+/i.test(t)) return false;
    return (
      /\*\*/.test(t) ||
      /\(\d{1,3}%/.test(t) ||
      /%?\s*match/i.test(t) ||
      /\bLPA\b/i.test(t) ||
      /₹/.test(t) ||
      /\bat\s+[A-Z]/.test(t) ||
      /[—–-]\s*\d/.test(t)
    );
  };

  const lines = text.split("\n");
  const filtered = lines.filter((line) => {
    const t = line.trim();
    if (looksLikeJobLine(t)) return false;
    if (/^[-*•]\s+\*\*/.test(t) && /match|LPA|₹/i.test(t)) return false;
    return true;
  });
  return filtered.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function prepareAssistantText(text: string, hasJobs: boolean): string {
  if (!hasJobs) return text;
  return stripJobListFromText(stripMarkdownTables(text));
}

function MessageBubble({
  message,
  isStreaming = false,
  onOptionSelect,
  actionCount,
  actions,
  jobs = [],
  applicationKits = [],
  jobFilters = {},
  conversationId,
  savedJobIds,
  onSavedChange,
  onRequestIntro,
  onApply,
  onWhyFit,
}: {
  message: Message;
  isStreaming?: boolean;
  onOptionSelect: (opt: string) => void;
  actionCount: number;
  actions: AgentAction[];
  jobs?: MatchedJob[];
  applicationKits?: ApplicationKit[];
  jobFilters?: JobCardFilters;
  conversationId?: string;
  savedJobIds?: Set<string>;
  onSavedChange?: (jobId: string, saved: boolean) => void;
  onRequestIntro?: (job: MatchedJob) => void;
  onApply?: (job: MatchedJob) => void;
  onWhyFit?: (job: MatchedJob) => void;
}) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const parsed = parseMessage(message.content);
  const text = prepareAssistantText(parsed.text, jobs.length > 0);
  const { options } = parsed;

  if (isSystem) {
    return (
      <div className="flex justify-center animate-fade-in">
        <div className="text-micro text-ink-500 bg-ink-50 border border-ink-100 rounded-full px-3 py-1.5 max-w-[90%]">
          <MessageText content={text} isUser={false} />
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[80%] bg-paper-1 border border-ink-200 rounded-lg rounded-br-sm px-5 py-3.5 shadow-1 space-y-1 text-ink-900">
          {message.content_type === "voice" && (
            <div className="flex items-center gap-1.5 text-micro text-ink-500">
              <Mic className="h-3 w-3" strokeWidth={1.5} />
              <span>Voice</span>
            </div>
          )}
          <MessageText content={text} isUser />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-fade-in">
      {/* Action timeline — shown above the reply that followed the actions */}
      {actionCount > 0 && (
        <ActivityTimeline
          count={actionCount}
          actions={actions}
          agentName="Aarya"
        />
      )}

      {/* Message text — full column width to align with the composer */}
      <div className="w-full space-y-1 rounded-lg border border-ink-100 bg-paper-1 px-4 py-3 shadow-sm">
        <MessageText content={text} isUser={false} isStreaming={isStreaming} />
        {message.spoken && !isStreaming && (
          <p className="text-micro text-ink-400 flex items-center gap-1">
            <Volume2 className="h-3 w-3" strokeWidth={1.5} />
            Played aloud
          </p>
        )}
      </div>

      {jobs.length > 0 && !isStreaming && (
        <ChatJobCards
          jobs={jobs}
          filters={jobFilters}
          conversationId={conversationId}
          savedJobIds={savedJobIds ?? new Set()}
          onSavedChange={onSavedChange ?? (() => undefined)}
          onRequestIntro={onRequestIntro}
          onApply={onApply}
          onWhyFit={onWhyFit}
        />
      )}

      {applicationKits.length > 0 && !isStreaming && (
        <ApplicationKitCards kits={applicationKits} />
      )}

      {/* Option cards */}
      {options.length > 0 && !isStreaming && (
        <div className="w-full space-y-2">
          <div className="rounded-xl border border-ink-200 overflow-hidden">
            {options.map((opt, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onOptionSelect(opt)}
                className={cn(
                  "w-full flex items-center justify-between px-4 py-3.5 text-left",
                  "text-body text-ink-900 hover:bg-ink-50 transition-colors duration-fast",
                  i !== 0 && "border-t border-ink-100"
                )}
              >
                <span>{opt}</span>
                <ChevronRight className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
              </button>
            ))}
          </div>
          <p className="text-small text-ink-500 ml-1">
            Or, answer in your own words below
          </p>
        </div>
      )}
    </div>
  );
}
