"use client";

import { useEffect, useState } from "react";
import { Button, Modal } from "@/components/ui";
import { VoiceSession } from "@/app/voice/VoiceSession";
import { ShieldCheck } from "@/components/brand/icons";

type VoiceDeepDiveModalProps = {
  open: boolean;
  onClose: () => void;
  candidateName?: string;
  scheduledSessionId?: string;
};

export function VoiceDeepDiveModal({
  open,
  onClose,
  candidateName,
  scheduledSessionId,
}: VoiceDeepDiveModalProps) {
  const [consentChecked, setConsentChecked] = useState(false);
  const [continued, setContinued] = useState(false);

  useEffect(() => {
    if (!open) {
      setConsentChecked(false);
      setContinued(false);
    }
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="15-min call with Aarya"
      description="A private conversation to improve your career recommendations."
      size="lg"
      className="max-h-[min(720px,92vh)] overflow-y-auto"
    >
      {continued ? (
        <VoiceSession
          candidateName={candidateName}
          embedded
          onComplete={onClose}
          consent={consentChecked}
          scheduledSessionId={scheduledSessionId}
        />
      ) : (
        <div className="space-y-5 pb-2">
          <div className="rounded-lg border border-ink-200 bg-ink-50 p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck
                className="mt-0.5 h-5 w-5 shrink-0 text-ink-700"
                strokeWidth={1.5}
                aria-hidden
              />
              <div className="space-y-2">
                <p className="text-small font-semibold text-ink-900">Before you continue</p>
                <ul className="list-disc space-y-1.5 pl-4 text-small text-ink-600">
                  <li>
                    Aarya uses this call to improve your candidate-owned profile and job
                    recommendations.
                  </li>
                  <li>Your transcript is private to you and Hireschema&apos;s processing.</li>
                  <li>Audio is not stored.</li>
                  <li>
                    Nothing from this call is shared with recruiters. Any future sharing
                    requires separate consent.
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <label className="flex cursor-pointer items-start gap-3 rounded-md border border-ink-200 p-3 text-small text-ink-700">
            <input
              type="checkbox"
              checked={consentChecked}
              onChange={(event) => setConsentChecked(event.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-ink-300 accent-ink-900"
            />
            <span>I understand and consent to this private career-discovery call.</span>
          </label>

          <div className="flex justify-end">
            <Button disabled={!consentChecked} onClick={() => setContinued(true)}>
              Continue
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
