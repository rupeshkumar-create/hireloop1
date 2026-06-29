"use client";

import { Mic } from "lucide-react";
import { cn } from "@/lib/utils";

export function AaryaFace({
  size = "md",
  withMic = false,
}: {
  size?: "xl" | "md" | "sm";
  withMic?: boolean;
}) {
  return (
    <div className="relative shrink-0 inline-flex">
      <div
        className={cn(
          "rounded-xl bg-ink-100 flex items-center justify-center text-ink-900",
          size === "xl" && "w-48 h-48",
          size === "md" && "w-14 h-14",
          size === "sm" && "w-10 h-10",
        )}
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
          aria-hidden
        >
          <path
            d="M11 19 Q16 14 21 17"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M39 17 Q44 14 49 19"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <ellipse cx="19" cy="26" rx="3" ry="3.5" fill="currentColor" />
          <ellipse cx="41" cy="26" rx="3" ry="3.5" fill="currentColor" />
          <path
            d="M30 28 L28 38 Q31 40 34 38"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M17 46 Q30 56 43 46"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {withMic && (
        <div className="absolute -bottom-1.5 -left-1.5 w-7 h-7 rounded-full bg-ink-900 flex items-center justify-center border-2 border-paper-0">
          <Mic className="h-3 w-3 text-paper-0" strokeWidth={2} />
        </div>
      )}
    </div>
  );
}
