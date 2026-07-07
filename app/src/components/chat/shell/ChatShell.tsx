"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Loader2, Send } from "@/components/brand/icons";
import { ChatBubble } from "@/components/ux/ChatBubble";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { ChatChip, ChatMessage } from "@/lib/chat/types";

export type ChatShellProps = {
  messages?: ChatMessage[];
  streamingText?: string;
  status?: string | null;
  chips?: ChatChip[];
  onChipClick?: (chip: ChatChip) => void;
  error?: string | null;
  onRetry?: () => void;
  input?: string;
  onInputChange?: (value: string) => void;
  onSend?: () => void;
  sending?: boolean;
  placeholder?: string;
  disabled?: boolean;
  header?: React.ReactNode;
  footer?: React.ReactNode;
  emptyState?: React.ReactNode;
  className?: string;
  messagesClassName?: string;
  /** Replace the default message list (Aarya job cards, kickoff, etc.). */
  messagesSlot?: React.ReactNode;
  /** Replace the default textarea composer (Aarya voice toolbar). */
  composerSlot?: React.ReactNode;
  /** External scroll anchor — e.g. Aarya passes its own ref. */
  messagesEndRef?: React.Ref<HTMLDivElement>;
  /** Extra values that should trigger scroll-to-bottom (Aarya streaming, voice, etc.). */
  scrollDeps?: unknown[];
};

export function ChatShell({
  messages = [],
  streamingText = "",
  status,
  chips = [],
  onChipClick,
  error,
  onRetry,
  input = "",
  onInputChange,
  onSend,
  sending = false,
  placeholder = "Type a message…",
  disabled = false,
  header,
  footer,
  emptyState,
  className,
  messagesClassName,
  messagesSlot,
  composerSlot,
  messagesEndRef: externalEndRef,
  scrollDeps = [],
}: ChatShellProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  // True while the viewport is pinned to the latest content. Flips off the moment
  // the user scrolls up so incoming job cards never yank them back down.
  const stickToBottomRef = useRef(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const isStreaming = Boolean(streamingText);
  const useDefaultMessages = messagesSlot === undefined;
  const useDefaultComposer = composerSlot === undefined;
  const scrollAnchorRef = externalEndRef ?? bottomRef;

  // How close to the bottom (px) still counts as "pinned".
  const NEAR_BOTTOM_PX = 120;

  const isNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
  }, []);

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = "smooth") => {
      if (typeof scrollAnchorRef !== "function") {
        scrollAnchorRef.current?.scrollIntoView({ behavior, block: "end" });
      }
      stickToBottomRef.current = true;
      setShowJumpToLatest(false);
    },
    [scrollAnchorRef],
  );

  // Track user scroll intent: pin to bottom only while already near the bottom.
  const handleScroll = useCallback(() => {
    const nearBottom = isNearBottom();
    stickToBottomRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom);
  }, [isNearBottom]);

  useEffect(() => {
    if (typeof scrollAnchorRef === "function") return;
    if (!stickToBottomRef.current) return;
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, streamingText, status, chips, messagesSlot, scrollAnchorRef, scrollDeps]);

  const showEmpty =
    useDefaultMessages &&
    messages.length === 0 &&
    !streamingText &&
    !sending;

  return (
    <div className={cn("flex flex-col min-h-0 h-full bg-paper-0", className)}>
      {header}

      <div className="relative flex-1 min-h-0 flex flex-col">
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className={cn(
          "flex-1 overflow-y-auto min-h-0",
          useDefaultMessages && "px-4 py-4 space-y-3",
          messagesClassName,
        )}
      >
        {useDefaultMessages ? (
          <>
            {showEmpty && emptyState}
            {messages.map((m) => (
              <ChatBubble
                key={m.id}
                role={m.role === "user" ? "user" : "assistant"}
              >
                <p className="text-small whitespace-pre-wrap">{m.content}</p>
              </ChatBubble>
            ))}
            {isStreaming && (
              <ChatBubble role="assistant">
                <p className="text-small whitespace-pre-wrap">{streamingText}</p>
              </ChatBubble>
            )}
            {sending && !isStreaming && (
              <div className="flex items-center gap-2 text-micro text-ink-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
                {status ?? "Thinking…"}
              </div>
            )}
            {!sending && status && (
              <p className="text-micro text-ink-500">{status}</p>
            )}
            {chips.length > 0 && !sending && !isStreaming && (
              <div className="flex flex-wrap gap-2 pt-1">
                {chips.map((chip) => (
                  <button
                    key={chip.id}
                    type="button"
                    onClick={() => onChipClick?.(chip)}
                    className="rounded-full border border-ink-200 bg-paper-1 px-3 py-1.5 text-micro text-ink-800 hover:border-accent hover:text-ink-900 transition-colors"
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          messagesSlot
        )}
        <div ref={scrollAnchorRef} />
      </div>

      {showJumpToLatest && (
        <button
          type="button"
          onClick={() => scrollToBottom("smooth")}
          aria-label="Jump to latest"
          className={cn(
            "absolute bottom-3 left-1/2 -translate-x-1/2 z-10",
            "flex items-center gap-1.5 rounded-full border border-ink-200 bg-paper-0",
            "px-3 py-1.5 text-micro font-medium text-ink-800 shadow-2",
            "hover:border-accent hover:text-ink-900 transition-colors",
          )}
        >
          <ChevronDown className="h-3.5 w-3.5" strokeWidth={2} />
          Jump to latest
        </button>
      )}
      </div>

      {useDefaultComposer ? (
        <div className="border-t border-ink-100 bg-paper-1 p-3 space-y-2 shrink-0">
          {error && (
            <div className="flex items-center justify-between gap-2">
              <p className="text-micro text-destructive">{error}</p>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="text-micro text-accent hover:underline shrink-0"
                >
                  Retry
                </button>
              )}
            </div>
          )}
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => onInputChange?.(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (!disabled && !sending && input.trim()) onSend?.();
                }
              }}
              rows={2}
              placeholder={placeholder}
              disabled={disabled || sending}
              className={cn(
                "flex-1 resize-none rounded-md border border-ink-100 bg-paper-0",
                "px-3 py-2 text-small text-ink-900 placeholder:text-ink-400",
                "outline-none focus:ring-2 focus:ring-accent-ring",
              )}
            />
            <Button
              variant="primary"
              size="sm"
              loading={sending}
              disabled={disabled || !input.trim() || sending}
              onClick={onSend}
              aria-label="Send message"
            >
              <Send className="h-4 w-4" strokeWidth={1.75} />
            </Button>
          </div>
          {footer}
        </div>
      ) : (
        <div className="shrink-0">{composerSlot}</div>
      )}
    </div>
  );
}
