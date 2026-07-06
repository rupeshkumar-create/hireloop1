"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Send, Zap } from "@/components/brand/icons";
import { useParams } from "next/navigation";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useVoice } from "@/lib/hooks/useVoice";
import {
  ActivityTimeline,
  type AgentAction,
} from "@/components/chat/ActivityTimeline";
import { ChatCandidateCards } from "@/components/chat/ChatCandidateCards";
import { MessageText } from "@/components/chat/MessageText";
import { RoleReadinessBar } from "@/components/recruiter/RoleReadinessBar";
import { RoleWorkspaceTabs } from "@/components/recruiter/RoleWorkspaceTabs";
import { ShareRoleLink } from "@/components/recruiter/ShareRoleLink";
import {
  fetchNityaChatHistory,
  getRole,
  movePipelineCandidate,
  publishAndRequestIntro,
  publishRole,
  requestCandidateIntro,
  sendNityaMessage,
  type RankedCandidate,
  type RoleReadiness,
  type SearchMeta,
} from "@/lib/api/recruiter";

type Message = {
  role: "user" | "assistant" | "system";
  content: string;
  candidates?: RankedCandidate[];
  searchMeta?: SearchMeta | null;
};

export default function RoleIntakePage() {
  const { id } = useParams<{ id: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [actionCount, setActionCount] = useState(0);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [briefDone, setBriefDone] = useState(false);
  const [chips, setChips] = useState<string[]>([]);
  const [turnCount, setTurnCount] = useState(0);
  const [maxTurns, setMaxTurns] = useState(3);
  const [readiness, setReadiness] = useState<RoleReadiness | null>(null);
  const [introingId, setIntroingId] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [published, setPublished] = useState(false);
  const [publicRoleUrl, setPublicRoleUrl] = useState<string | null>(null);
  const [roleTitle, setRoleTitle] = useState<string | null>(null);
  const [lastSearchMeta, setLastSearchMeta] = useState<SearchMeta | null>(null);
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const bootstrappedRef = useRef(false);

  const {
    isRecording,
    error: voiceError,
    startRecording,
    stopRecording,
  } = useVoice();

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, chips]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  function applyChatResponse(res: Awaited<ReturnType<typeof sendNityaMessage>>) {
    setChips(res.chip_suggestions || []);
    setTurnCount(res.turn_count);
    setMaxTurns(res.max_turns);
    if (res.readiness) setReadiness(res.readiness);
    setActionCount(res.action_count);
    if (Array.isArray(res.actions)) setActions(res.actions);
    if (res.brief_generated || res.brief_complete) setBriefDone(true);
    if (res.published != null) setPublished(res.published);
    if (res.search_meta) setLastSearchMeta(res.search_meta);
    return res;
  }

  useEffect(() => {
    let cancelled = false;
    bootstrappedRef.current = false;

    (async () => {
      try {
        const role = await getRole(id);
        if (cancelled) return;
        if (role.title) setRoleTitle(role.title);
        if (role.readiness) setReadiness(role.readiness);
        if (role.hiring_brief) setBriefDone(true);
        if (role.public_role_url) setPublicRoleUrl(role.public_role_url);

        const history = await fetchNityaChatHistory(id);
        if (cancelled) return;

        setPublished(history.published);

        if (history.messages.length > 0) {
          const restored: Message[] = history.messages
            .filter((m) => m.role !== "system")
            .map((m) => ({
              role: m.role as "user" | "assistant",
              content: m.content,
            }));
          const lastWithCandidates =
            history.candidates.length > 0
              ? {
                  ...restored[restored.length - 1],
                  candidates: history.candidates,
                }
              : null;
          if (lastWithCandidates && restored.length > 0) {
            restored[restored.length - 1] = lastWithCandidates;
          }
          setMessages(restored);
          bootstrappedRef.current = true;
          return;
        }

        const res = applyChatResponse(await sendNityaMessage(id, "", true));
        if (cancelled) return;
        bootstrappedRef.current = true;
        setMessages([
          {
            role: "assistant",
            content: res.reply,
            candidates: res.candidates?.length ? res.candidates : undefined,
            searchMeta: res.search_meta,
          },
        ]);
      } catch (e) {
        if (!cancelled) {
          setMessages([
            { role: "assistant", content: `⚠ ${(e as Error).message}` },
          ]);
        }
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleMicToggle = useCallback(async () => {
    if (loading || bootstrapping || voiceProcessing) return;
    if (isRecording) {
      setVoiceProcessing(true);
      try {
        const text = (await stopRecording()).trim();
        if (text) setInput(text);
      } finally {
        setVoiceProcessing(false);
      }
    } else {
      await startRecording();
    }
  }, [
    bootstrapping,
    isRecording,
    loading,
    startRecording,
    stopRecording,
    voiceProcessing,
  ]);

  async function send(contentOverride?: string) {
    const content = (contentOverride ?? input).trim();
    if (!content || loading || bootstrapping) return;
    setInput("");
    setChips([]);
    setMessages((m) => [...m, { role: "user", content }]);
    setLoading(true);

    try {
      const res = applyChatResponse(await sendNityaMessage(id, content));
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.reply,
          candidates: res.candidates?.length ? res.candidates : undefined,
          searchMeta: res.search_meta,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠ ${(e as Error).message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleChip(chip: string) {
    if (chip.toLowerCase().includes("publish")) {
      setPublishing(true);
      try {
        const result = await publishRole(id);
        setPublished(true);
        if (result.public_role_url) setPublicRoleUrl(result.public_role_url);
        setMessages((m) => [
          ...m,
          {
            role: "system",
            content: result.public_role_url
              ? "Role published — share the public link with candidates."
              : "Role published to the candidate marketplace.",
          },
        ]);
      } catch (e) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `⚠ ${(e as Error).message}` },
        ]);
      } finally {
        setPublishing(false);
      }
      return;
    }
    await send(chip);
  }

  async function handleRequestIntro(candidate: RankedCandidate) {
    setIntroingId(candidate.candidate_id);
    try {
      await requestCandidateIntro(id, candidate.candidate_id);
      markIntroRequested(candidate);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠ ${(e as Error).message}` },
      ]);
    } finally {
      setIntroingId(null);
    }
  }

  async function handlePublishAndIntro(candidate: RankedCandidate) {
    setIntroingId(candidate.candidate_id);
    try {
      await publishAndRequestIntro(id, candidate.candidate_id);
      setPublished(true);
      const role = await getRole(id);
      if (role.public_role_url) setPublicRoleUrl(role.public_role_url);
      markIntroRequested(candidate);
      setMessages((m) => [
        ...m,
        {
          role: "system",
          content: `Published role and requested intro for ${candidate.display_name || "candidate"}.`,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠ ${(e as Error).message}` },
      ]);
    } finally {
      setIntroingId(null);
    }
  }

  function markIntroRequested(candidate: RankedCandidate) {
    setMessages((m) =>
      m.map((msg) => {
        if (!msg.candidates) return msg;
        return {
          ...msg,
          candidates: msg.candidates.map((c) =>
            c.candidate_id === candidate.candidate_id
              ? { ...c, stage: "intro_requested" }
              : c
          ),
        };
      })
    );
    setMessages((m) => [
      ...m,
      {
        role: "system",
        content: `Intro requested for ${candidate.display_name || candidate.current_title || "candidate"}.`,
      },
    ]);
  }

  async function handleShortlist(candidate: RankedCandidate) {
    if (!candidate.pipeline_id) return;
    try {
      await movePipelineCandidate(id, candidate.pipeline_id, "shortlisted");
      setMessages((m) =>
        m.map((msg) => {
          if (!msg.candidates) return msg;
          return {
            ...msg,
            candidates: msg.candidates.map((c) =>
              c.candidate_id === candidate.candidate_id
                ? { ...c, stage: "shortlisted" }
                : c
            ),
          };
        })
      );
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠ ${(e as Error).message}` },
      ]);
    }
  }

  async function handlePass(candidate: RankedCandidate) {
    if (!candidate.pipeline_id) return;
    try {
      await movePipelineCandidate(id, candidate.pipeline_id, "archived");
      setMessages((m) =>
        m.map((msg) => {
          if (!msg.candidates) return msg;
          return {
            ...msg,
            candidates: msg.candidates.filter(
              (c) => c.candidate_id !== candidate.candidate_id
            ),
          };
        })
      );
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠ ${(e as Error).message}` },
      ]);
    }
  }

  const showChips = chips.length > 0 && !loading;

  return (
    <main className="flex flex-col h-full bg-paper-0 overflow-hidden">
      <RoleWorkspaceTabs roleId={id} active="chat" title={roleTitle} />
      <header className="shrink-0 border-b border-ink-100 bg-paper-1">
        <div className="h-14 flex items-center gap-3 px-4">
          <div className="w-8 h-8 rounded-full bg-ink-900 flex items-center justify-center shrink-0">
            <span className="text-paper-0 text-small font-semibold">N</span>
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-body font-semibold text-ink-900">Nitya</p>
            <p className="text-micro text-ink-500">
              {briefDone
                ? published
                  ? "Find candidates & request intros"
                  : "Publish role to request intros"
                : `Turn ${turnCount}/${maxTurns} — quick gaps only`}
            </p>
          </div>

          <ShareRoleLink publicRoleUrl={publicRoleUrl} className="hidden sm:block" />

          {actionCount > 0 && (
            <Badge tone="accent">
              <Zap className="h-3 w-3 mr-1" strokeWidth={2} />
              {actionCount}
            </Badge>
          )}
        </div>

        {readiness && (
          <div className="px-4 pb-3">
            <RoleReadinessBar readiness={readiness} />
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-2xl mx-auto space-y-4">
          {bootstrapping && messages.length === 0 && (
            <div className="text-center text-ink-500 text-small pt-12">
              Nitya is reviewing your brief…
            </div>
          )}

          {messages.map((m, i) => {
            if (m.role === "system") {
              return (
                <div key={i} className="flex justify-center py-2">
                  <span className="text-small text-ink-500 bg-ink-50 border border-ink-100 rounded-full px-3 py-1">
                    {m.content}
                  </span>
                </div>
              );
            }

            return (
              <div key={i} className="space-y-3">
                <div
                  className={cn(
                    "flex",
                    m.role === "user" ? "justify-end" : "justify-start"
                  )}
                >
                  {m.role === "assistant" && (
                    <div className="w-7 h-7 rounded-full bg-ink-900 flex items-center justify-center mr-2.5 mt-1 shrink-0">
                      <span className="text-paper-0 text-micro font-semibold">N</span>
                    </div>
                  )}
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-4 py-3 text-body leading-relaxed",
                      m.role === "user"
                        ? "bg-ink-900 text-paper-0 rounded-br-sm"
                        : "bg-paper-1 text-ink-900 border border-ink-100 shadow-1 rounded-bl-sm"
                    )}
                  >
                    <MessageText content={m.content} isUser={m.role === "user"} />
                  </div>
                </div>

                {m.role === "assistant" &&
                  (Boolean(m.candidates?.length) || m.searchMeta) && (
                  <div className="pl-[38px]">
                    <ChatCandidateCards
                      candidates={m.candidates ?? []}
                      introingId={introingId}
                      published={published}
                      searchMeta={m.searchMeta ?? lastSearchMeta}
                      onRequestIntro={(c) => void handleRequestIntro(c)}
                      onPublishAndIntro={(c) => void handlePublishAndIntro(c)}
                      onShortlist={(c) => void handleShortlist(c)}
                      onPass={(c) => void handlePass(c)}
                    />
                  </div>
                )}
              </div>
            );
          })}

          {actionCount > 0 && !loading && !bootstrapping && (
            <div className="pl-[38px]">
              <ActivityTimeline
                count={actionCount}
                actions={actions}
                agentName="Nitya"
              />
            </div>
          )}

          {loading && (
            <div className="flex justify-start">
              <div className="w-7 h-7 rounded-full bg-ink-900 flex items-center justify-center mr-2.5 shrink-0">
                <span className="text-paper-0 text-micro font-semibold">N</span>
              </div>
              <div className="bg-paper-1 border border-ink-100 shadow-1 rounded-2xl rounded-bl-sm px-4 py-3">
                <p className="text-small text-ink-500">Thinking…</p>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="shrink-0 border-t border-ink-100 bg-paper-1 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
        <div className="max-w-2xl mx-auto space-y-2">
          {showChips && (
            <div className="flex flex-wrap gap-2">
              {chips.map((chip) => (
                <Button
                  key={chip}
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={publishing && chip.toLowerCase().includes("publish")}
                  onClick={() => void handleChip(chip)}
                >
                  {chip}
                </Button>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2 rounded-xl border border-ink-100 bg-paper-0 px-3 py-2 focus-within:border-ink-300 focus-within:ring-2 focus-within:ring-accent/15 transition-all">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder={
                isRecording
                  ? "Listening… tap mic when done"
                  : briefDone
                    ? "Ask Nitya to find candidates, shortlist, or publish…"
                    : "Message Nitya…"
              }
              rows={1}
              disabled={loading || bootstrapping || isRecording || voiceProcessing}
              className="flex-1 resize-none bg-transparent text-body text-ink-900 placeholder:text-ink-300 outline-none min-h-[24px] max-h-36"
            />
            <button
              type="button"
              onClick={() => void handleMicToggle()}
              disabled={loading || bootstrapping || voiceProcessing}
              aria-label={isRecording ? "Stop recording" : "Start voice input"}
              className={cn(
                "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                isRecording
                  ? "bg-destructive text-paper-0 animate-pulse"
                  : "text-ink-500 hover:bg-ink-50 hover:text-ink-900"
              )}
            >
              <Mic className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
            <button
              type="button"
              onClick={() => void send()}
              disabled={!input.trim() || loading || bootstrapping}
              className={cn(
                "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                input.trim() && !loading
                  ? "bg-accent text-on-accent"
                  : "text-ink-300 cursor-not-allowed"
              )}
            >
              <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          </div>
          {voiceError && (
            <p className="text-micro text-destructive">{voiceError}</p>
          )}
        </div>
      </div>
    </main>
  );
}
