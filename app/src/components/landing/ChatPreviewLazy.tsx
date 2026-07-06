"use client";

import dynamic from "next/dynamic";

type Audience = "candidate" | "recruiter";

type ChatPreviewLazyProps = {
  audience?: Audience;
};

function ChatPreviewSkeleton() {
  return (
    <div
      className="w-full overflow-hidden rounded-xl border border-ink-100 bg-paper-1 shadow-2"
      aria-hidden
    >
      <div className="border-b border-ink-100 px-4 py-3">
        <div className="h-7 w-32 animate-pulse rounded-md bg-ink-100" />
      </div>
      <div className="h-[320px] space-y-3 bg-paper-0 p-4">
        <div className="ml-auto h-10 w-3/4 animate-pulse rounded-2xl bg-ink-100" />
        <div className="h-16 w-4/5 animate-pulse rounded-2xl bg-ink-50" />
        <div className="ml-auto h-10 w-2/3 animate-pulse rounded-2xl bg-ink-100" />
      </div>
      <div className="border-t border-ink-100 px-4 py-3">
        <div className="h-10 animate-pulse rounded-xl bg-ink-50" />
      </div>
    </div>
  );
}

const ChatPreview = dynamic(
  () => import("./ChatPreview").then((mod) => mod.ChatPreview),
  {
    ssr: false,
    loading: () => <ChatPreviewSkeleton />,
  },
);

export function ChatPreviewLazy({ audience = "candidate" }: ChatPreviewLazyProps) {
  return <ChatPreview audience={audience} />;
}
