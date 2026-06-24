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
 *   - Phone button: opens /voice for a full voice session
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Route,
  Briefcase,
  Check,
  ChevronRight,
  IndianRupee,
  Loader2,
  Mic,
  Paperclip,
  Phone,
  Search,
  Sparkles,
  Square,
  TrendingUp,
  Upload,
  Users,
  Volume2,
  VolumeX,
} from "lucide-react";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
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
  readStoredAaryaSession,
  storeAaryaSession,
  streamAaryaMessage,
} from "@/lib/chat/aaryaStream";
import { isJobApplicationIntent, isJobSearchIntent } from "@/lib/chat/messageIntent";
import { useVoice } from "@/lib/hooks/useVoice";
import { cn } from "@/lib/utils";
import type { MatchedJob } from "@/lib/api/matches";
import {
  fetchMyProfile,
  type MyProfileData,
  type RemotePreference,
} from "@/lib/api/profile";
import { AgentThinkingIndicator } from "./AgentThinkingIndicator";
import { ActivityTimeline, type AgentAction } from "./ActivityTimeline";
import { ChatContextBar } from "./ChatContextBar";
import { ProfileCompletionFlow } from "./ProfileCompletionFlow";
import { ChatJobCards } from "./ChatJobCards";
import { VoiceTranscriptReview } from "./VoiceTranscriptReview";
import {
  CareerPathOptionCards,
  type CareerPathOption,
} from "@/components/career/CareerPathOptionCards";

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
  /**
   * true  = user hasn't uploaded a resume or completed a voice session yet.
   *         Show "Upload resume" as the primary card.
   * false = user is unlocked; show "My job matches" as the primary card.
   */
  isLocked?: boolean;
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
  isLocked = false,
  injectedMessage,
  savedJobIds = new Set(),
  onSavedChange,
  onRequestIntro,
}: ChatInterfaceProps) {
  const [messages, setMessages]       = useState<Message[]>(initialMessages);
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
  const [preferTextMode, setPreferTextMode] = useState(false);
  const [streamRecovery, setStreamRecovery] = useState<StreamRecovery | null>(null);

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
    stopSpeaking,
    interimTranscript,
    audioLevel,
  } = useVoice();

  const messagesEndRef  = useRef<HTMLDivElement>(null);
  const textareaRef     = useRef<HTMLTextAreaElement>(null);
  const fileInputRef    = useRef<HTMLInputElement>(null);
  const abortRef        = useRef<AbortController | null>(null);

  // ── Effects ────────────────────────────────────────────────────────────

  useEffect(() => {
    void warmupChatContext().then(setWarmup).catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, pendingVoiceTranscript]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
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

  // Action counter poll — only once a session exists.
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
    const ms = isStreaming ? 1000 : 3000;
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

      const contentType = options.contentType ?? "text";
      const shouldSpeakReply =
        options.speakReply ?? (contentType === "voice" && !preferTextMode);

      setPendingVoiceTranscript(null);
      setStreamRecovery(null);
      setStreamingApplicationKits([]);
      streamingApplicationKitsRef.current = [];
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

      const finalize = () => {
        if (streamFinalized || !accumulated) return;
        streamFinalized = true;
        finalReply = accumulated;
        const kitsForMessage =
          streamingApplicationKitsRef.current.length > 0
            ? streamingApplicationKitsRef.current
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
          },
        ]);
        setStreamingContent("");
        setStreamingApplicationKits([]);
        streamingApplicationKitsRef.current = [];
      };

      try {
        const currentSessionId = await ensureAaryaSession(
          sessionIdRef.current ?? readStoredAaryaSession(),
          (id) => {
            sessionIdRef.current = id;
            setSessionId(id);
            storeAaryaSession(id);
            onSessionCreated?.(id);
          }
        );

        await streamAaryaMessage(
          currentSessionId,
          trimmed,
          contentType,
          {
            onStatus: (status) => setThinkingStatus(status),
            onText: (_chunk, full) => {
              accumulated = full;
              setThinkingStatus(null);
              setStreamingContent(full);
            },
          },
          abortRef.current.signal
        );

        if (!streamFinalized && accumulated.trim()) {
          finalize();
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          const message =
            err instanceof Error && err.message
              ? err.message
              : "Something went wrong. Please try again.";

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
                content: `Sorry, I ran into an issue. ${message}`,
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
        const shouldSpeak = shouldSpeakReply && finalReply.length > 0;
        if (shouldSpeak) {
          setMessages((prev) => {
            if (!prev.length) return prev;
            const last = prev[prev.length - 1];
            if (last.role !== "assistant") return prev;
            return prev.map((m, i) =>
              i === prev.length - 1 ? { ...m, spoken: true } : m
            );
          });
          void speak(finalReply.slice(0, 2000), "aarya");
        }
      }
    },
    [isStreaming, speak, onSessionCreated, actionCount, preferTextMode]
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

  // ── Voice ───────────────────────────────────────────────────────────────

  const handleMicToggle = useCallback(async () => {
    if (!VOICE_FEATURE_ENABLED) return;
    if (isRecording) {
      setVoiceProcessing(true);
      try {
        const transcript = await stopRecording().catch(() => "");
        if (transcript.trim()) {
          setPendingVoiceTranscript(transcript.trim());
        } else {
          appendSystemNote(
            "I didn’t catch that. Tap the mic and try again, or type it instead."
          );
        }
      } finally {
        setVoiceProcessing(false);
      }
    } else {
      stopSpeaking();
      setPendingVoiceTranscript(null);
      await startRecording();
    }
  }, [appendSystemNote, isRecording, startRecording, stopRecording, stopSpeaking]);

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
        try {
          await apiAuthFetch(`/api/v1/resumes/${data.resume_id}/apply-to-profile`, {
            method: "POST",
          });
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

  // ── Render ──────────────────────────────────────────────────────────────

  const isEmpty = messages.length === 0 && !streamingContent;

  return (
    <div className={cn("flex flex-col h-full bg-paper-0", className)}>

      {/* ── Messages ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-5 py-8 space-y-6">
          {isEmpty ? (
            <EmptyState
              onPick={(p) => void sendMessage(p)}
              onUploadResume={() => fileInputRef.current?.click()}
              isLocked={isLocked}
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
                  />
                );
              })}

              {/* Streaming partial */}
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
                <div className="rounded-xl border border-ink-200 bg-paper-1 px-4 py-3 space-y-2 max-w-[88%]">
                  <p className="text-small text-ink-600">
                    Connection dropped — your partial reply is saved above.
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      void sendMessage(streamRecovery.continuePrompt)
                    }
                    className="text-small font-medium text-ink-900 underline underline-offset-2 hover:text-accent"
                  >
                    Continue
                  </button>
                </div>
              )}

              {isUploading && (
                <AgentThinkingIndicator variant="processing" />
              )}

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

              <div ref={messagesEndRef} />
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
      </div>

      {/* ── Composer ──────────────────────────────────────────────────── */}
      <div className="shrink-0 bg-paper-0 px-4 pt-2 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        <div className="max-w-2xl mx-auto space-y-2">
          {!isLocked && (
            <ChatContextBar
              profile={warmup?.profile ?? null}
              matchCount={warmup?.matchCount ?? null}
              profileCompleteness={warmup?.profileCompleteness ?? null}
              onChipClick={() => setShowProfileFlow(true)}
            />
          )}

          {isRecording && interimTranscript && (
            <div className="rounded-xl border border-ink-200 bg-paper-1 px-3 py-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="text-micro uppercase tracking-wide text-ink-400">
                  Listening
                </p>
                <div
                  className="h-1 w-16 overflow-hidden rounded-full bg-ink-100"
                  aria-hidden
                >
                  <div
                    className="h-full rounded-full bg-accent transition-all duration-100"
                    style={{ width: `${Math.max(8, Math.round(audioLevel * 100))}%` }}
                  />
                </div>
              </div>
              <p className="text-small text-ink-800">{interimTranscript}</p>
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

          {(isRecording || voiceProcessing || isPlaying) && (
            <div className="flex items-center justify-between gap-2 px-1">
              <p className="text-micro text-ink-500">
                {isRecording
                  ? "Listening…"
                  : voiceProcessing
                    ? "Processing voice…"
                    : "Speaking…"}
              </p>
              <div className="flex items-center gap-2">
                {isPlaying && (
                  <button
                    type="button"
                    onClick={stopSpeaking}
                    className="text-micro text-ink-600 underline underline-offset-2 hover:text-ink-900"
                  >
                    Stop speaking
                  </button>
                )}
                {isRecording && (
                  <button
                    type="button"
                    onClick={() => void handleMicToggle()}
                    className="text-micro text-ink-700 underline underline-offset-2 hover:text-ink-900"
                  >
                    Cancel
                  </button>
                )}
                {(isPlaying || isRecording) && !preferTextMode && (
                  <button
                    type="button"
                    onClick={() => {
                      stopSpeaking();
                      setPreferTextMode(true);
                    }}
                    className="text-micro text-ink-600 underline underline-offset-2 hover:text-ink-900"
                  >
                    Switch to text
                  </button>
                )}
              </div>
            </div>
          )}

          <div
            className={cn(
              "bg-paper-1 rounded-lg border border-ink-200 shadow-1",
              "transition-shadow duration-fast",
              "focus-within:shadow-2 focus-within:border-ink-300"
            )}
          >
            {/* Text area */}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isRecording
                  ? "Listening… tap stop to review your message."
                  : pendingVoiceTranscript
                    ? "Edit your voice message above, then send."
                    : "Ask Aarya anything…"
              }
              rows={2}
              disabled={
                isStreaming || isRecording || Boolean(pendingVoiceTranscript)
              }
              className={cn(
                "w-full bg-transparent resize-none text-body text-ink-900",
                "placeholder:text-ink-400 focus:outline-none leading-relaxed",
                "px-5 pt-4 pb-2 max-h-[160px] disabled:opacity-60"
              )}
            />

            {/* Bottom toolbar */}
            <div className="flex items-center justify-between px-4 pb-3 pt-1">
              {/* Left: resume upload */}
              <button
                type="button"
                title={isUploading ? "Uploading resume…" : "Upload resume (PDF or DOCX)"}
                disabled={isUploading || isStreaming}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                  isUploading || isStreaming
                    ? "text-ink-300 cursor-not-allowed"
                    : "text-ink-400 hover:text-ink-900 hover:bg-ink-50"
                )}
              >
                {isUploading
                  ? <Loader2 className="h-[18px] w-[18px] animate-spin" strokeWidth={1.5} />
                  : <Paperclip className="h-[18px] w-[18px]" strokeWidth={1.5} />
                }
              </button>
              {/* Hidden file input */}
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

              {/* Right: phone + voice */}
              <div className="flex items-center gap-2">
                {VOICE_FEATURE_ENABLED && (
                  <Link
                    href="/voice"
                    title="Voice call with Aarya"
                    className="w-8 h-8 rounded-lg text-ink-400 hover:text-ink-900 hover:bg-ink-50 flex items-center justify-center transition-colors"
                  >
                    <Phone className="h-[17px] w-[17px]" strokeWidth={1.5} />
                  </Link>
                )}

                {/* Voice mic — filled dark pill like J&J */}
                {VOICE_FEATURE_ENABLED ? (
                  <button
                    type="button"
                    onClick={() => void handleMicToggle()}
                    disabled={
                      isStreaming ||
                      voiceProcessing ||
                      Boolean(pendingVoiceTranscript)
                    }
                    aria-pressed={isRecording}
                    title={isRecording ? "Stop and review transcript" : "Speak to Aarya"}
                    className={cn(
                      "w-10 h-10 rounded-full flex items-center justify-center transition-colors duration-fast",
                      isRecording
                        ? "bg-destructive text-paper-0 animate-pulse"
                        : preferTextMode
                          ? "bg-ink-200 text-ink-700 hover:bg-ink-300"
                          : "bg-ink-900 text-paper-0 hover:bg-ink-800",
                      (isStreaming || voiceProcessing) &&
                        "opacity-40 cursor-not-allowed"
                    )}
                  >
                    {isRecording ? (
                      <Square className="h-3.5 w-3.5" strokeWidth={2} fill="currentColor" />
                    ) : preferTextMode ? (
                      <VolumeX className="h-[17px] w-[17px]" strokeWidth={2} />
                    ) : (
                      <Mic className="h-[17px] w-[17px]" strokeWidth={2} />
                    )}
                  </button>
                ) : (
                  /* No voice: show a plain send button */
                  <button
                    type="button"
                    onClick={() => void sendMessage(input)}
                    disabled={!input.trim() || isStreaming}
                    aria-label="Send"
                    className={cn(
                      "w-10 h-10 rounded-full flex items-center justify-center transition-colors",
                      input.trim() && !isStreaming
                        ? "bg-ink-900 text-paper-0 hover:bg-ink-800"
                        : "bg-ink-100 text-ink-300 cursor-not-allowed"
                    )}
                  >
                    {isStreaming ? (
                      <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
                    ) : (
                      <Mic className="h-4 w-4" strokeWidth={1.5} />
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>

          {voiceError && (
            <div className="mt-2 text-center space-y-1">
              <p className="text-small text-ink-700">{voiceError}</p>
              <p className="text-micro text-ink-500">
                You can keep typing below. To use voice, allow microphone access in
                your browser settings and reload.
              </p>
            </div>
          )}

          {VOICE_FEATURE_ENABLED && !preferTextMode && (
            <p className="text-micro text-ink-400 text-center px-2">
              Voice is processed for transcription only; raw audio is not stored
              (DPDP).{" "}
              <button
                type="button"
                className="underline underline-offset-2 hover:text-ink-600"
                onClick={() => setPreferTextMode(true)}
              >
                Text only
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
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
  /** If "upload", clicking fires onUploadResume. Otherwise sends the message. */
  kind: "upload" | "message";
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

/** Three starter actions — ranked by what moves the candidate forward right now. */
function buildSmartStarterCards(
  profile: MyProfileData | null,
  findJobsMessage: string,
  profileSparse: boolean,
): ActionCardDef[] {
  const jobMatches: ActionCardDef = {
    Icon: Briefcase,
    title: "My job matches",
    description: "Your top-ranked roles, best first",
    kind: "message",
    message: "Show me my best job matches",
  };

  const findJobs: ActionCardDef = {
    Icon: Search,
    title: "Find jobs",
    description: "Search tuned to your role, skills, and city",
    kind: "message",
    message: findJobsMessage,
  };

  const improveProfile: ActionCardDef = {
    Icon: TrendingUp,
    title: "Improve my profile",
    description: "Close gaps that weaken your match scores",
    kind: "message",
    message:
      "Review my profile and tell me the most impactful gaps to fix to rank higher in matches.",
  };

  const salary: ActionCardDef = {
    Icon: IndianRupee,
    title: "What could I earn?",
    description: "Realistic CTC range for your next move",
    kind: "message",
    message:
      "Based on my profile, experience, and the India market, what CTC range could I realistically target next?",
  };

  const intros: ActionCardDef = {
    Icon: Users,
    title: "Hiring manager intros",
    description: "Warm intros to decision makers",
    kind: "message",
    message: "Help me connect with hiring managers for roles I'm interested in",
  };

  const careerPaths: ActionCardDef = {
    Icon: Route,
    title: "My career paths",
    description: "Top 3 directions — pick one to prioritize",
    kind: "message",
    message:
      "Show me my top 3 career paths and help me pick one to prioritize before searching jobs.",
  };

  if (profileSparse) {
    return [
      { ...improveProfile, primary: true },
      findJobs,
      { ...jobMatches, description: "See what's matching while you finish up" },
    ];
  }

  const c = profile?.candidate;
  const hasTarget = Boolean(c?.looking_for?.trim() || c?.current_title?.trim());

  return [
    { ...careerPaths, primary: true },
    { ...jobMatches, primary: false },
    intros,
    hasTarget ? findJobs : salary,
  ];
}

function EmptyState({
  onPick,
  onUploadResume,
  isLocked = false,
}: {
  onPick: (text: string) => void;
  onUploadResume: () => void;
  isLocked?: boolean;
}) {
  // Pull the candidate's profile so the "Find jobs" action can be grounded in
  // their real role / location / skills rather than a canned search. Only when
  // unlocked — a locked user has no profile worth personalising on yet.
  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [showPathPicker, setShowPathPicker] = useState(false);
  useEffect(() => {
    if (isLocked) return;
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
  }, [isLocked]);

  const findJobsMessage = buildFindJobsMessage(profile);

  // Meaningful pre-selection: at low profile completeness the highest-value next
  // step is closing profile gaps (better matches downstream), not browsing yet.
  // Once the profile is solid, default to job matches. We never pre-check more
  // than one — this is a "recommended starting point", not a multi-select.
  const c = profile?.candidate;
  const profileSparse =
    !c ||
    c.profile_complete === false ||
    !c.current_title?.trim() ||
    (c.skills ?? []).filter((s) => s.trim()).length < 3;

  const cards: ActionCardDef[] = isLocked
    ? [
        {
          Icon: Upload,
          title: "Upload your resume",
          description: "Fastest way to unlock matches and chat",
          primary: true,
          kind: "upload",
        },
      ]
    : buildSmartStarterCards(profile, findJobsMessage, profileSparse);

  // Aarya-led, state-aware greeting — the empty state should feel like a recruiter
  // saying hello, not a menu of buttons.
  const firstName = (profile?.user?.full_name || "").trim().split(" ")[0] || "there";
  const greeting = isLocked
    ? `Hi ${firstName}, I'm Aarya. Let's get you set up — share your CV and I'll build your profile and surface roles that actually fit.`
    : profileSparse
      ? `Hi ${firstName}, I'm Aarya — your recruiter here. Your profile's almost there; let's close the last gaps so your matches sharpen.`
      : `Hi ${firstName}, I'm Aarya — your recruiter here. Pick a career path or jump straight to matches.`;

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
        <p className="text-small text-ink-400 leading-relaxed">
          Tap a suggestion, or just tell me what you&apos;re looking for.
        </p>
      </div>

      {!isLocked && !profileSparse && (
        <div className="w-full text-left">
          {showPathPicker ? (
            <CareerPathOptionCards
              compact
              onSelectPath={handlePathSelect}
              className="mb-2"
            />
          ) : (
            <button
              type="button"
              onClick={() => setShowPathPicker(true)}
              className="w-full flex items-center gap-2.5 rounded-lg border border-ink-200 bg-paper-1 px-3 py-2 text-left hover:bg-ink-50 hover:border-ink-300 transition-colors"
            >
              <Route className="h-4 w-4 text-ink-500 shrink-0" strokeWidth={1.5} />
              <span className="text-small font-medium text-ink-900">
                View top 3 career paths
              </span>
            </button>
          )}
        </div>
      )}

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

      {isLocked && (
        <div className="text-micro text-ink-500 text-center space-y-1 max-w-sm">
          <p>
            Upload a resume to unlock personalised job matches, or complete a{" "}
            <Link
              href="/voice"
              className="underline underline-offset-2 hover:text-ink-700 transition-colors"
            >
              15‑min voice onboarding
            </Link>{" "}
            with Aarya.
          </p>
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

      {/* Message text */}
      <div className="max-w-[88%] space-y-1">
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
        />
      )}

      {applicationKits.length > 0 && !isStreaming && (
        <ApplicationKitCards kits={applicationKits} />
      )}

      {/* Option cards */}
      {options.length > 0 && !isStreaming && (
        <div className="max-w-[88%] space-y-2">
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
