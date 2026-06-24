import { cn } from "@/lib/utils";

/** Shared bubble styling for Aarya + IntroChat parity. */
export function ChatBubble({
  role,
  children,
  className,
}: {
  role: "user" | "assistant" | "other";
  children: React.ReactNode;
  className?: string;
}) {
  const isUser = role === "user";
  return (
    <div
      className={cn(
        "max-w-[85%] rounded-lg px-4 py-2.5 text-body leading-relaxed",
        isUser
          ? "ml-auto bg-ink-900 text-paper-0"
          : "mr-auto bg-paper-1 border border-ink-100 text-ink-900",
        className,
      )}
    >
      {children}
    </div>
  );
}
