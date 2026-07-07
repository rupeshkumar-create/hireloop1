"use client";

import { RichMarkdown } from "@/components/ui/RichMarkdown";

export function MessageText({
  content,
  isUser,
  isStreaming,
}: {
  content: string;
  isUser: boolean;
  isStreaming?: boolean;
}) {
  if (isUser) {
    return (
      <div className="text-body leading-relaxed whitespace-pre-wrap">
        {content}
      </div>
    );
  }

  return (
    <div>
      <RichMarkdown content={content} variant="chat" />
      {isStreaming && (
        <span className="inline-block h-4 w-0.5 bg-ink-700 ml-0.5 align-middle animate-pulse" />
      )}
    </div>
  );
}
