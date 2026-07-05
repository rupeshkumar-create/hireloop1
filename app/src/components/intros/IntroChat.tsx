"use client";

/**
 * IntroChat — the direct candidate↔recruiter thread for an accepted intro.
 * Used from both the candidate intros page and the recruiter inbox; `side`
 * selects which auth-scoped API to hit.
 */

import { useEffect, useRef, useState } from "react";
import { Send } from "@/components/brand/icons";
import {
  fetchIntroThread,
  sendIntroMessage,
  type IntroMessage,
  type IntroChatSide,
} from "@/lib/api/introChat";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui";
import { ChatBubble } from "@/components/ux";
import { cn } from "@/lib/utils";

export function IntroChat({
  introId,
  side,
}: {
  introId: string;
  side: IntroChatSide;
}) {
  const [messages, setMessages] = useState<IntroMessage[]>([]);
  const [canChat, setCanChat] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  // Viewer's own side, used to flag incoming realtime rows as mine/theirs.
  const youRef = useRef<IntroChatSide>(side);

  function appendUnique(msg: IntroMessage) {
    setMessages((prev) =>
      prev.some((m) => m.id === msg.id) ? prev : [...prev, msg]
    );
  }

  useEffect(() => {
    let cancelled = false;
    fetchIntroThread(introId, side)
      .then((t) => {
        if (cancelled) return;
        setMessages(t.messages);
        setCanChat(t.can_chat);
        youRef.current = t.you;
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't load chat");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [introId, side]);

  // Live-stream new messages from the other party (RLS scopes this to parties).
  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel(`intro_messages:${introId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "intro_messages",
          filter: `intro_request_id=eq.${introId}`,
        },
        (payload) => {
          const r = payload.new as {
            id: string;
            sender_type: IntroChatSide;
            body: string;
            created_at: string;
          };
          appendUnique({
            id: r.id,
            sender_type: r.sender_type,
            body: r.body,
            created_at: r.created_at,
            mine: r.sender_type === youRef.current,
          });
        }
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [introId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function send() {
    const body = draft.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      const msg = await sendIntroMessage(introId, side, body);
      appendUnique(msg); // realtime will echo the same id — deduped
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="rounded-lg border border-ink-100 bg-paper-1 mt-3 overflow-hidden">
      {/* Messages */}
      <div className="max-h-72 overflow-y-auto px-3 py-3 space-y-2 bg-paper-0">
        {loading && (
          <div className="h-12 rounded bg-ink-100 animate-skeleton" />
        )}
        {!loading && messages.length === 0 && (
          <p className="text-small text-ink-400 text-center py-4">
            No messages yet — say hello to kick things off.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={cn("flex", m.mine ? "justify-end" : "justify-start")}>
            <ChatBubble role={m.mine ? "user" : "other"}>{m.body}</ChatBubble>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {error && (
        <p className="text-destructive text-micro px-3 py-1">{error}</p>
      )}

      {/* Composer */}
      <div className="flex items-end gap-2 border-t border-ink-100 p-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          rows={1}
          placeholder={canChat ? "Write a message…" : "Chat opens once accepted"}
          disabled={!canChat || sending}
          className="flex-1 resize-none rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-small text-ink-900 focus:border-accent focus:outline-none disabled:opacity-60"
        />
        <Button
          variant="primary"
          size="sm"
          onClick={() => void send()}
          loading={sending}
          disabled={!canChat || !draft.trim()}
          leftIcon={<Send className="h-3.5 w-3.5" strokeWidth={1.5} />}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
