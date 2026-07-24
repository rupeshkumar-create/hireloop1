"use client";

import { PhoneOff } from "@/components/brand/icons";
import { ComposerWaveform } from "./ComposerWaveform";
import { BTN_COMPOSER_ICON } from "@/lib/button-classes";
import { cn } from "@/lib/utils";

function formatClock(seconds: number): string {
  const m = Math.floor(Math.max(0, seconds) / 60);
  const s = Math.max(0, seconds) % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

type InThreadCallBannerProps = {
  secondsLeft: number;
  audioLevel?: number;
  onEnd?: () => void;
  className?: string;
};

/** Status strip for an in-thread career call. Controls live in VoiceSession below. */
export function InThreadCallBanner({
  secondsLeft,
  audioLevel = 0,
  onEnd,
  className,
}: InThreadCallBannerProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2.5",
        className,
      )}
      role="status"
      aria-live="polite"
    >
      <div className="min-w-0 flex items-center gap-2">
        <ComposerWaveform
          level={audioLevel}
          active
          mode="listening"
        />
        <div className="min-w-0">
          <p className="text-micro font-medium text-ink-900">
            Career call · {formatClock(secondsLeft)} left
          </p>
          <p className="text-micro text-ink-600 truncate">
            Same chat thread — use the controls below
          </p>
        </div>
      </div>
      {onEnd && (
        <button
          type="button"
          className={cn(BTN_COMPOSER_ICON, "text-destructive shrink-0")}
          aria-label="Leave call"
          title="Leave call (end from Aarya controls to save progress)"
          onClick={onEnd}
        >
          <PhoneOff className="h-4 w-4" strokeWidth={1.5} />
        </button>
      )}
    </div>
  );
}
