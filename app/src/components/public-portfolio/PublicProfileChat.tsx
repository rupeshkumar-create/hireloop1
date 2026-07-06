"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { MessageCircle, Send, X } from "@/components/brand/icons";
import { AaryaFace } from "@/components/aarya/AaryaFace";
import { ChatBubble } from "@/components/ux/ChatBubble";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import {
  fetchPublicProfileChat,
  getOrCreateVisitorSessionId,
  sendPublicProfileChat,
  type PublicChatMessage,
} from "@/lib/api/publicProfile";

type PublicProfileChatProps = {
  slug: string;
  candidateLabel: string;
};

export function PublicProfileChat({ slug, candidateLabel }: PublicProfileChatProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<PublicChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visitorId, setVisitorId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setVisitorId(getOrCreateVisitorSessionId(slug));
  }, [slug]);

  const loadHistory = useCallback(async () => {
    if (!visitorId) return;
    const rows = await fetchPublicProfileChat(slug, visitorId);
    setMessages(rows);
  }, [slug, visitorId]);

  useEffect(() => {
    if (!open || !visitorId) return;
    void loadHistory();
  }, [open, visitorId, loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function handleSend() {
    const text = input.trim();
    if (!text || !visitorId || sending) return;
    setSending(true);
    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    try {
      const result = await sendPublicProfileChat(slug, visitorId, text);
      setMessages(result.messages);
    } catch (err) {
      setError((err as Error).message);
      setMessages((prev) => prev.slice(0, -1));
      setInput(text);
    } finally {
      setSending(false);
    }
  }

  const greeting =
    messages.length === 0
      ? `Hi! I'm Aarya. Ask me anything about ${candidateLabel}'s background, skills, or what they're looking for next.`
      : null;

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn(
            "fixed z-40 bottom-6 right-6 flex items-center gap-2",
            "rounded-full bg-accent text-on-accent px-5 py-3 shadow-1",
            "hover:bg-accent-hover transition-colors",
            "text-small font-semibold",
          )}
          aria-label="Open chat with Aarya"
        >
          <MessageCircle className="h-5 w-5" strokeWidth={1.75} />
          <span className="hidden sm:inline">Chat with Aarya</span>
        </button>
      )}

      {open && (
        <div
          className={cn(
            "fixed z-50 inset-x-0 bottom-0 sm:inset-auto sm:bottom-6 sm:right-6",
            "sm:w-[min(100vw-2rem,24rem)] sm:max-h-[32rem]",
            "flex flex-col bg-paper-1 border border-ink-100 shadow-1",
            "rounded-t-lg sm:rounded-lg overflow-hidden",
            "h-[min(85vh,32rem)] sm:h-[min(70vh,32rem)]",
          )}
          role="dialog"
          aria-label={`Chat about ${candidateLabel}`}
        >
          <header className="flex items-center gap-3 border-b border-ink-100 px-4 py-3 bg-paper-0 shrink-0">
            <AaryaFace size="sm" />
            <div className="min-w-0 flex-1">
              <p className="text-small font-semibold text-ink-900 truncate">Aarya</p>
              <p className="text-micro text-ink-500 truncate">
                About {candidateLabel}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1.5 text-ink-500 hover:text-ink-900 transition-colors"
              aria-label="Close chat"
            >
              <X className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </header>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-paper-0">
            {greeting && (
              <ChatBubble role="assistant">
                <p className="text-small whitespace-pre-wrap">{greeting}</p>
              </ChatBubble>
            )}
            {messages.map((m, i) => (
              <ChatBubble key={`${m.role}-${i}`} role={m.role === "user" ? "user" : "assistant"}>
                <p className="text-small whitespace-pre-wrap">{m.content}</p>
              </ChatBubble>
            ))}
            {sending && (
              <p className="text-micro text-ink-500 animate-pulse">Aarya is typing…</p>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-ink-100 bg-paper-1 p-3 space-y-2 shrink-0">
            {error && (
              <p className="text-micro text-destructive">{error}</p>
            )}
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
                rows={2}
                placeholder="Ask about their experience…"
                className={cn(
                  "flex-1 resize-none rounded-md border border-ink-100 bg-paper-0",
                  "px-3 py-2 text-small text-ink-900 placeholder:text-ink-400",
                  "outline-none focus:ring-2 focus:ring-accent-ring",
                )}
                disabled={sending}
              />
              <Button
                variant="primary"
                size="sm"
                loading={sending}
                disabled={!input.trim() || sending}
                onClick={() => void handleSend()}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" strokeWidth={1.75} />
              </Button>
            </div>
            <p className="text-micro text-ink-500 text-center">
              Hiring?{" "}
              <Link
                href={`/signup?role=recruiter&from=${encodeURIComponent(`/p/${slug}`)}`}
                className="text-accent hover:underline"
              >
                Join as a recruiter
              </Link>
            </p>
          </div>
        </div>
      )}
    </>
  );
}
