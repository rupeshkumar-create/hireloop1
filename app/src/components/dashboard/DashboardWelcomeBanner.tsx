"use client";

import { useEffect, useState } from "react";
import { X } from "@/components/brand/icons";
import { AaryaBubble } from "@/components/aarya/AaryaBubble";
import { AaryaFace } from "@/components/aarya/AaryaFace";
import { consumeDashboardWelcome } from "@/lib/dashboard-welcome";
import { cn } from "@/lib/utils";

type DashboardWelcomeBannerProps = {
  firstName?: string;
  matchCount?: number | null;
  onDismiss?: () => void;
};

export function DashboardWelcomeBanner({
  firstName,
  matchCount,
  onDismiss,
}: DashboardWelcomeBannerProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(consumeDashboardWelcome());
  }, []);

  if (!visible) return null;

  const name = firstName ?? "there";
  const matches =
    matchCount != null && matchCount > 0
      ? `${matchCount} ${matchCount === 1 ? "match" : "matches"} ranked for you`
      : "your Jobs panel is ready";

  function dismiss() {
    setVisible(false);
    onDismiss?.();
  }

  return (
    <div
      className={cn(
        "mx-5 mt-4 flex items-start gap-3 rounded-xl border border-accent/20",
        "bg-gradient-to-r from-accent/5 to-paper-1 p-4 animate-fade-in",
      )}
      role="status"
    >
      <AaryaFace size="sm" />
      <AaryaBubble className="flex-1 min-w-0 !rounded-lg !rounded-tl-sm">
        <p className="text-small font-semibold text-ink-900">You&apos;re in, {name}</p>
        <p className="text-small text-ink-600 mt-1 leading-relaxed">
          {matches}. Tap <strong className="font-medium text-ink-800">Show me jobs</strong> when
          you want Aarya to start the feed.
        </p>
      </AaryaBubble>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss welcome message"
        className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors"
      >
        <X className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </div>
  );
}
