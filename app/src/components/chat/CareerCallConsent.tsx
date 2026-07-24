"use client";

import { ShieldCheck } from "@/components/brand/icons";
import { Button } from "@/components/ui";

type CareerCallConsentProps = {
  onConfirm: () => void;
  onCancel: () => void;
};

export function CareerCallConsent({ onConfirm, onCancel }: CareerCallConsentProps) {
  return (
    <div className="rounded-lg border border-ink-200 bg-paper-1 p-4 space-y-4">
      <div className="flex items-start gap-3">
        <ShieldCheck
          className="mt-0.5 h-5 w-5 shrink-0 text-ink-700"
          strokeWidth={1.5}
          aria-hidden
        />
        <div className="space-y-2">
          <p className="text-small font-semibold text-ink-900">
            15-min call with Aarya
          </p>
          <ul className="list-disc space-y-1.5 pl-4 text-small text-ink-600">
            <li>
              Aarya uses this call to improve your candidate-owned profile and job
              recommendations.
            </li>
            <li>Your transcript is private to you and Hireschema&apos;s processing.</li>
            <li>Audio is not stored.</li>
            <li>
              Nothing from this call is shared with recruiters without separate consent.
            </li>
          </ul>
        </div>
      </div>
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Not now
        </Button>
        <Button type="button" size="sm" onClick={onConfirm}>
          Start call
        </Button>
      </div>
    </div>
  );
}
