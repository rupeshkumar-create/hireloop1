"use client";

import { cn } from "@/lib/utils";

/** Nitya avatar — recruiter agent (distinct from Aarya's candidate face). */
export function NityaFace({
  size = "md",
}: {
  size?: "xl" | "md" | "sm";
}) {
  return (
    <div
      className={cn(
        "rounded-xl bg-accent/10 border-2 border-accent/30 flex items-center justify-center text-accent",
        size === "xl" && "w-48 h-48",
        size === "md" && "w-14 h-14",
        size === "sm" && "w-10 h-10",
      )}
      aria-hidden
    >
      <svg
        viewBox="0 0 60 60"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={cn(
          size === "xl" && "w-28 h-28",
          size === "md" && "w-8 h-8",
          size === "sm" && "w-6 h-6",
        )}
      >
        <path
          d="M11 19 Q16 14 21 17"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <path
          d="M39 19 Q44 14 49 17"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
        <circle cx="20" cy="28" r="2.5" fill="currentColor" />
        <circle cx="40" cy="28" r="2.5" fill="currentColor" />
        <path
          d="M22 38 Q30 44 38 38"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}
