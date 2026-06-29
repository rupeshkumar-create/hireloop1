import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function AaryaBubble({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-paper-1 rounded-lg rounded-tl-sm px-5 py-4 shadow-1 border border-ink-100",
        className,
      )}
    >
      {children}
    </div>
  );
}
