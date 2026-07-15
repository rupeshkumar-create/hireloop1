"use client";

import { Check, Mail, Calendar, Shield } from "@/components/brand/icons";
import { Button } from "@/components/ui";

const BENEFITS = [
  {
    Icon: Mail,
    title: "Send intros from your Gmail",
    body: "Warm intros and follow-ups go from your address — hiring managers see you, not a no-reply.",
  },
  {
    Icon: Calendar,
    title: "Add Meet links to booked calls",
    body: "When you book a voice session with Aarya, we can create the calendar event with a Meet link.",
  },
  {
    Icon: Shield,
    title: "Send-only — we never read your inbox",
    body: "You approve every outreach. We only use gmail.send (and calendar.events if you booked a call).",
  },
] as const;

type GoogleConnectedBannerProps = {
  gmailEmail: string | null;
  onDismiss: () => void;
};

/** Post-connect confirmation shown on chat after Google OAuth succeeds. */
export function GoogleConnectedBanner({
  gmailEmail,
  onDismiss,
}: GoogleConnectedBannerProps) {
  return (
    <div
      className="mx-auto w-full max-w-2xl rounded-xl border border-ink-100 bg-paper-1 px-4 py-4 shadow-sm sm:px-5"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-900 text-paper-0">
          <Check className="h-4 w-4" strokeWidth={2.5} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-small font-semibold text-ink-900">Google connected</p>
          <p className="mt-0.5 text-micro text-ink-600">
            {gmailEmail
              ? `You're connected as ${gmailEmail}. Aarya can send approved intros from this inbox.`
              : "You're connected. Aarya can send approved intros from your Gmail."}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onDismiss} className="shrink-0">
          Got it
        </Button>
      </div>

      <ul className="mt-4 grid gap-3 sm:grid-cols-3">
        {BENEFITS.map(({ Icon, title, body }) => (
          <li key={title} className="min-w-0">
            <div className="flex items-center gap-1.5 text-micro font-medium text-ink-900">
              <Icon className="h-3.5 w-3.5 shrink-0 text-ink-500" strokeWidth={1.5} />
              {title}
            </div>
            <p className="mt-1 text-micro leading-relaxed text-ink-500">{body}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
