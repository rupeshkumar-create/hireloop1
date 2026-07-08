"use client";

/**
 * IntroChat — the direct candidate↔recruiter thread for an intro.
 * For recruiter→candidate requests, the recruiter can send the first note while
 * the candidate hasn't accepted yet; the candidate can only reply once accepted.
 * Used from both the candidate intros page and the recruiter inbox; `side`
 * selects which auth-scoped API to hit.
 */

import { useCallback, useEffect, useRef, useState } from "react";
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

const POLL_FALLBACK_MS = 4_000;

export function IntroChat({
  introId,
  side,
  fillHeight = false,
}: {
  introId: string;
  side: IntroChatSide;
  /** Expand to fill parent flex column (inbox split view). */
  fillHeight?: boolean;
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
  const realtimeOkRef = useRef(false);
  const lastSeenCountRef = useRef(0);

  const appendUnique = useCallback((msg: IntroMessage) => {
    setMessages((prev) => {
      if (prev.some((m) => m.id === msg.id)) return prev;
      return [...prev, msg];
    });
  }, []);

  const mergeThread = useCallback((incoming: IntroMessage[], nextCanChat: boolean, you: IntroChatSide) => {
    youRef.current = you;
    setCanChat(nextCanChat);
    setMessages((prev) => {
      if (prev.length === 0) return incoming;
      const byId = new Map(prev.map((m) => [m.id, m]));
      for (const m of incoming) byId.set(m.id, m);
      return Array.from(byId.values()).sort((a, b) =>
        a.created_at.localeCompare(b.created_at),
      );
    });
  }, []);

  const refreshThread = useCallback(async () => {
    try {
      const t = await fetchIntroThread(introId, side);
      mergeThread(t.messages, t.can_chat, t.you);
      lastSeenCountRef.current = t.messages.length;
      setError(null);
    } catch (e: unknown) {
      // Keep the open thread usable; only surface hard failures on first load.
      if (lastSeenCountRef.current === 0) {
        setError(e instanceof Error ? e.message : "Couldn't load chat");
      }
    }
  }, [introId, mergeThread, side]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    realtimeOkRef.current = false;
    lastSeenCountRef.current = 0;
    fetchIntroThread(introId, side)
      .then((t) => {
        if (cancelled) return;
        mergeThread(t.messages, t.can_chat, t.you);
        lastSeenCountRef.current = t.messages.length;
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
  }, [introId, mergeThread, side]);

  // Live-stream new messages (Realtime) + quiet poll fallback if the channel
  // never reaches SUBSCRIBED (common when RLS/auth JWT is stale).
  useEffect(() => {
    const supabase = createClient();
    let cancelled = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    async function subscribe() {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (token) {
        await supabase.realtime.setAuth(token);
      }
      if (cancelled) return;

      channel = supabase
        .channel(`intro_messages:${introId}:${side}`)
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
          },
        )
        .subscribe((status) => {
          realtimeOkRef.current = status === "SUBSCRIBED";
        });
    }

    void subscribe();

    const pollId = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      // Quiet safety net: if Realtime never subscribed (RLS/JWT), pull via API.
      if (!realtimeOkRef.current) void refreshThread();
    }, POLL_FALLBACK_MS);

    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshThread();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      window.clearInterval(pollId);
      document.removeEventListener("visibilitychange", onVisible);
      if (channel) void supabase.removeChannel(channel);
    };
  }, [appendUnique, introId, refreshThread, side]);

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
      appendUnique(msg); // realtime/poll may echo the same id — deduped
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send");
    } finally {
      setSending(false);
    }
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-ink-100 bg-paper-1 overflow-hidden flex flex-col",
        fillHeight ? "h-full min-h-0 mt-0" : "mt-3",
      )}
    >
      {/* Messages */}
      <div
        className={cn(
          "overflow-y-auto px-3 py-3 space-y-2 bg-paper-0 flex-1 min-h-0",
          !fillHeight && "max-h-72",
        )}
      >
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
