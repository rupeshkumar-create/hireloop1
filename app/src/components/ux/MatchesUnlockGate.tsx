"use client";

import Link from "next/link";
import { FileText, Mic, Sparkles } from "lucide-react";
import { Button, Card, CardBody } from "@/components/ui";

type MatchesUnlockGateProps = {
  hasResume?: boolean;
  hasVoice?: boolean;
  onUploadResume?: () => void;
};

/** Invitation-style gate — blurred preview, not a paywall. */
export function MatchesUnlockGate({
  hasResume = false,
  hasVoice = false,
  onUploadResume,
}: MatchesUnlockGateProps) {
  const unlocked = hasResume || hasVoice;
  if (unlocked) return null;

  return (
    <div className="relative overflow-hidden rounded-xl border border-ink-100">
      <div className="pointer-events-none select-none blur-sm opacity-60 p-6 space-y-3" aria-hidden>
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 rounded-lg bg-ink-50 border border-ink-100" />
        ))}
      </div>
      <Card className="absolute inset-0 m-4 flex items-center justify-center bg-paper-0/95 border-ink-100 shadow-2">
        <CardBody className="text-center max-w-md space-y-4">
          <Sparkles className="h-8 w-8 mx-auto text-accent" strokeWidth={1.5} />
          <h2 className="text-h2 text-ink-900">You&apos;re one step from matches</h2>
          <p className="text-small text-ink-500">
            Upload a resume or complete a 15-minute call with Aarya. We&apos;ll unlock your
            ranked job feed in your market.
          </p>
          <div className="flex flex-col sm:flex-row gap-2 justify-center">
            {onUploadResume ? (
              <Button onClick={onUploadResume} leftIcon={<FileText className="h-4 w-4" />}>
                Upload resume
              </Button>
            ) : (
              <Link
                href="/dashboard?panel=profile"
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-accent px-4 text-body font-medium text-on-accent hover:bg-accent-hover"
              >
                <FileText className="h-4 w-4" />
                Upload resume
              </Link>
            )}
            <Link
              href="/voice"
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-ink-200 bg-transparent px-4 text-body font-medium text-ink-900 hover:bg-ink-50 hover:border-ink-300"
            >
              <Mic className="h-4 w-4" />
              Talk to Aarya
            </Link>
          </div>
          <p className="text-micro text-ink-400">
            Prefer chat? Tell Aarya &quot;build my profile&quot; — no resume required.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
