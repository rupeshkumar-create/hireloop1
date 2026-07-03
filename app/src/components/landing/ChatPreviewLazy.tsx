"use client";

import dynamic from "next/dynamic";

function ChatPreviewSkeleton() {
  return (
    <div
      className="w-full overflow-hidden rounded-xl border border-ink-100 bg-paper-1 shadow-2"
      aria-hidden
    >
      <div className="border-b border-ink-100 px-4 py-3">
        <div className="h-7 w-32 rounded-md bg-ink-100 animate-pulse" />
      </div>
      <div className="h-[320px] bg-paper-0 p-4 space-y-3">
        <div className="ml-auto h-10 w-3/4 rounded-2xl bg-ink-100 animate-pulse" />
        <div className="h-16 w-4/5 rounded-2xl bg-ink-50 animate-pulse" />
        <div className="ml-auto h-10 w-2/3 rounded-2xl bg-ink-100 animate-pulse" />
      </div>
      <div className="border-t border-ink-100 px-4 py-3">
        <div className="h-10 rounded-xl bg-ink-50 animate-pulse" />
      </div>
    </div>
  );
}

export const ChatPreviewLazy = dynamic(
  () => import("./ChatPreview").then((mod) => mod.ChatPreview),
  {
    ssr: false,
    loading: () => <ChatPreviewSkeleton />,
  },
);
