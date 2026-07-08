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
          ? "ml-auto border-2 border-black bg-accent text-on-accent shadow-[0_0_0_2px_#b5ff6b,0_0_0_4px_#000000]"
          : "mr-auto bg-paper-1 border border-ink-100 text-ink-900",
        className,
      )}
    >
      {children}
    </div>
  );
}
