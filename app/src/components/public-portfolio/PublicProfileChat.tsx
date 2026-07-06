"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { MessageCircle } from "@/components/brand/icons";
import { AaryaFace } from "@/components/aarya/AaryaFace";
import { ChatShellDrawer } from "@/components/chat/shell/ChatShellDrawer";
import type { ChatChip, ChatMessage } from "@/lib/chat/types";
import {
  fetchPublicProfileChat,
  getOrCreateVisitorSessionId,
  streamPublicProfileChat,
} from "@/lib/api/publicProfile";

const PORTFOLIO_CHIPS: ChatChip[] = [
  {
    id: "roles",
    label: "What roles are they open to?",
    message: "What roles are they open to?",
  },
  {
    id: "summary",
    label: "Summarize for my hiring manager",
    message: "Summarize this candidate in 3 bullets for a hiring manager.",
  },
  {
    id: "intro",
    label: "Request intro",
    message: "How do I request an intro to this candidate on Hireloop?",
  },
];

type PublicProfileChatProps = {
  slug: string;
  candidateLabel: string;
};

export function PublicProfileChat({ slug, candidateLabel }: PublicProfileChatProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [chips, setChips] = useState<ChatChip[]>(PORTFOLIO_CHIPS);
  const [error, setError] = useState<string | null>(null);
  const [visitorId, setVisitorId] = useState<string | null>(null);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);

  useEffect(() => {
    setVisitorId(getOrCreateVisitorSessionId(slug));
  }, [slug]);

  const shellMessages = useMemo(() => messages, [messages]);

  const loadHistory = useCallback(async () => {
    if (!visitorId) return;
    const rows = await fetchPublicProfileChat(slug, visitorId);
    setMessages(
      rows.map((m, i) => ({
        id: `hist-${i}`,
        role: m.role,
        content: m.content,
        created_at: m.created_at ?? undefined,
      })),
    );
  }, [slug, visitorId]);

  useEffect(() => {
    if (!open || !visitorId) return;
    void loadHistory();
  }, [open, visitorId, loadHistory]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!visitorId || !text.trim() || sending) return;
      const trimmed = text.trim();
      setSending(true);
      setError(null);
      setStreamingText("");
      setStatus(null);
      setLastFailedMessage(null);
      setInput("");
      setMessages((prev) => [
        ...prev,
        { id: `user-${Date.now()}`, role: "user", content: trimmed },
      ]);
      try {
        const reply = await streamPublicProfileChat(slug, visitorId, trimmed, {
          onStatus: (s) => setStatus(s),
          onText: (_chunk, accumulated) => setStreamingText(accumulated),
          onChips: (next) => setChips(next),
        });
        setMessages((prev) => [
          ...prev,
          { id: `assistant-${Date.now()}`, role: "assistant", content: reply },
        ]);
        setStreamingText("");
        setStatus(null);
      } catch (err) {
        setError((err as Error).message);
        setLastFailedMessage(trimmed);
        setMessages((prev) => prev.slice(0, -1));
        setInput(trimmed);
        setStreamingText("");
      } finally {
        setSending(false);
      }
    },
    [sending, slug, visitorId],
  );

  const emptyState = (
    <p className="text-small text-ink-600 text-left">
      Hi! I&apos;m Aarya. Ask me about {candidateLabel}&apos;s background, skills, or
      what they&apos;re looking for next.
    </p>
  );

  return (
    <ChatShellDrawer
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      fabLabel="Chat with Aarya"
      fabIcon={<MessageCircle className="h-5 w-5" strokeWidth={1.75} />}
      ariaLabel={`Chat about ${candidateLabel}`}
      header={
        <div className="flex items-center gap-3 px-4 py-3 min-w-0">
          <AaryaFace size="sm" />
          <div className="min-w-0">
            <p className="text-small font-semibold text-ink-900 truncate">Aarya</p>
            <p className="text-micro text-ink-500 truncate">About {candidateLabel}</p>
          </div>
        </div>
      }
      messages={shellMessages}
      streamingText={streamingText}
      status={status}
      chips={chips}
      onChipClick={(chip) => void sendMessage(chip.message)}
      error={error}
      onRetry={
        lastFailedMessage
          ? () => void sendMessage(lastFailedMessage)
          : undefined
      }
      input={input}
      onInputChange={setInput}
      onSend={() => void sendMessage(input)}
      sending={sending}
      placeholder="Ask about their experience…"
      emptyState={emptyState}
      footer={
        <p className="text-micro text-ink-500 text-center">
          Hiring?{" "}
          <Link
            href={`/signup?role=recruiter&from=${encodeURIComponent(`/p/${slug}`)}`}
            className="text-accent hover:underline"
          >
            Join as a recruiter
          </Link>
        </p>
      }
    />
  );
}
