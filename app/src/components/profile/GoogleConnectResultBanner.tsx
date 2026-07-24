"use client";

import { AlertCircle, Check } from "@/components/brand/icons";
import { Button } from "@/components/ui";
import { startGoogleConnect } from "@/lib/api/gmail";
import { useState } from "react";

export function gmailErrorCopy(reason: string | null): { title: string; body: string } {
  switch (reason) {
    case "invalid_client":
      return {
        title: "Google connection failed (app credentials)",
        body: "Hireschema’s Google OAuth client secret is invalid or revoked. Ask the team to create a new client secret in Google Cloud and update Railway GOOGLE_CLIENT_SECRET, then try Connect Google again.",
      };
    case "invalid_grant":
      return {
        title: "Google connection expired",
        body: "The Google sign-in code expired or was already used. Tap Try again to connect Google once more.",
      };
    case "bad_state":
      return {
        title: "Google connection timed out",
        body: "That connect link expired (they last about 10 minutes). Tap Try again.",
      };
    case "no_candidate":
      return {
        title: "Finish candidate setup first",
        body: "Complete onboarding as a job seeker, then connect Google from Profile.",
      };
    default:
      return {
        title: "Couldn't connect Google",
        body: "Something went wrong finishing Google sign-in. Stay signed in to Hireschema, then try Connect Google again from chat or Profile.",
      };
  }
}

type Props =
  | {
      variant: "error";
      reason: string | null;
      onDismiss: () => void;
    }
  | {
      variant: "connected";
      gmailEmail: string | null;
      onDismiss: () => void;
    };

/** Persistent banner after Google OAuth returns (success or error). */
export function GoogleConnectResultBanner(props: Props) {
  const [busy, setBusy] = useState(false);

  if (props.variant === "connected") {
    return (
      <div
        className="mx-auto w-full max-w-2xl rounded-xl border border-ink-100 bg-paper-1 px-4 py-4 sm:px-5"
        role="status"
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-900 text-paper-0">
            <Check className="h-4 w-4" strokeWidth={2.5} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-small font-semibold text-ink-900">Google connected</p>
            <p className="mt-0.5 text-micro text-ink-600">
              {props.gmailEmail
                ? `Connected as ${props.gmailEmail}. Aarya can send approved intros from this inbox.`
                : "Connected. Aarya can send approved intros from your Gmail."}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={props.onDismiss}>
            Got it
          </Button>
        </div>
      </div>
    );
  }

  const copy = gmailErrorCopy(props.reason);

  async function retry() {
    setBusy(true);
    try {
      await startGoogleConnect();
    } catch {
      setBusy(false);
    }
  }

  return (
    <div
      className="mx-auto w-full max-w-2xl rounded-xl border border-ink-200 bg-paper-1 px-4 py-4 sm:px-5"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-100 text-ink-800">
          <AlertCircle className="h-4 w-4" strokeWidth={2} />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-small font-semibold text-ink-900">{copy.title}</p>
          <p className="text-micro leading-relaxed text-ink-600">{copy.body}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button size="sm" loading={busy} onClick={() => void retry()}>
              Try Connect Google again
            </Button>
            <Button variant="ghost" size="sm" onClick={props.onDismiss}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
