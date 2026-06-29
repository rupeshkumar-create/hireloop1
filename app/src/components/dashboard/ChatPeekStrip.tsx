"use client";

import { MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type ChatPeekStripProps = {
  onOpenChat: () => void;
  className?: string;
};

export function ChatPeekStrip({ onOpenChat, className }: ChatPeekStripProps) {
  return (
    <button
      type="button"
      onClick={onOpenChat}
      className={cn(
        "fixed inset-x-3 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-[25]",
        "flex items-center justify-center gap-2 rounded-full",
        "border border-ink-200 bg-paper-1/95 backdrop-blur-sm shadow-2",
        "px-4 py-2.5 text-small font-medium text-ink-800",
        "hover:bg-paper-0 hover:border-ink-300 transition-colors duration-fast",
        "md:hidden animate-fade-in",
        className,
      )}
      aria-label="Close panel and open chat with Aarya"
    >
      <MessageCircle className="h-4 w-4 text-accent shrink-0" strokeWidth={1.5} />
      <span>Aarya is ready — tap to chat</span>
    </button>
  );
}
