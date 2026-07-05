"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "@/components/brand/icons";
import { cn } from "@/lib/utils";

export function CollapsibleSection({
  title,
  description,
  children,
  defaultOpen = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-lg border border-ink-100 bg-paper-1 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-ink-50 transition-colors"
      >
        <div className="min-w-0">
          <p className="text-small font-semibold text-ink-900">{title}</p>
          {description && (
            <p className="text-micro text-ink-500 mt-0.5 truncate">{description}</p>
          )}
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-ink-400 shrink-0 transition-transform duration-fast",
            open && "rotate-180",
          )}
          strokeWidth={1.5}
        />
      </button>
      {open && <div className="px-4 pb-4 pt-0 border-t border-ink-50">{children}</div>}
    </div>
  );
}
