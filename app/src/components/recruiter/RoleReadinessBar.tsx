"use client";

import { Check, Circle } from "lucide-react";
import type { RoleReadiness } from "@/lib/api/recruiter";
import { cn } from "@/lib/utils";

export function RoleReadinessBar({ readiness }: { readiness: RoleReadiness }) {
  const pct = Math.round((readiness.done_count / readiness.total) * 100);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-small font-medium text-ink-900">
          Role ready — {pct}%
        </p>
        <p className="text-micro text-ink-500">
          {readiness.ready_for_search ? "Ready to search" : "Add JD or comp to search"}
        </p>
      </div>

      <div className="h-1.5 rounded-full bg-ink-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-accent transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {readiness.items.map((item) => (
          <span
            key={item.key}
            className={cn(
              "inline-flex items-center gap-1 text-micro",
              item.done ? "text-ink-700" : "text-ink-400"
            )}
          >
            {item.done ? (
              <Check className="h-3 w-3 text-accent" strokeWidth={2} />
            ) : (
              <Circle className="h-3 w-3" strokeWidth={1.5} />
            )}
            {item.label}
            {!item.done && item.key === "comp" && (
              <span className="text-warning">⚠</span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
