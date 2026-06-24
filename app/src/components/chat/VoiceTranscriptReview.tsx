"use client";

import { Mic, Send, X } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

type VoiceTranscriptReviewProps = {
  transcript: string;
  onChange: (value: string) => void;
  onSend: () => void;
  onDiscard: () => void;
  className?: string;
};

export function VoiceTranscriptReview({
  transcript,
  onChange,
  onSend,
  onDiscard,
  className,
}: VoiceTranscriptReviewProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-accent/30 bg-paper-1 p-3 space-y-2 animate-slide-up",
        className
      )}
    >
      <div className="flex items-center gap-2 text-micro text-ink-500">
        <Mic className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
        <span>Voice transcript — edit if needed, then send</span>
      </div>
      <textarea
        value={transcript}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        className="w-full resize-none rounded-lg border border-ink-200 bg-paper-0 px-3 py-2 text-small text-ink-900 focus:outline-none focus:ring-2 focus:ring-ink-900/20"
        aria-label="Edit voice transcript before sending"
      />
      <div className="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDiscard} leftIcon={<X className="h-3.5 w-3.5" />}>
          Discard
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={onSend}
          disabled={!transcript.trim()}
          leftIcon={<Send className="h-3.5 w-3.5" />}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
