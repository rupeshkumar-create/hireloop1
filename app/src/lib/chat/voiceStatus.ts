/**
 * Maps Aarya SSE tool-status events to spoken filler clips and ETA labels.
 */

const STATUS_META: Record<
  string,
  { spoken: string; etaSec: number }
> = {
  "Reading your profile…": {
    spoken: "Let me check your profile.",
    etaSec: 4,
  },
  "I'm checking your profile…": {
    spoken: "Let me check your profile.",
    etaSec: 4,
  },
  "Mapping your career path…": {
    spoken: "I'm mapping your career path.",
    etaSec: 6,
  },
  "I'm mapping the best next steps…": {
    spoken: "I'm mapping your career path.",
    etaSec: 6,
  },
  "Searching roles in your market…": {
    spoken: "I'm searching roles in your market for you.",
    etaSec: 8,
  },
  "I'm searching roles in your market now…": {
    spoken: "I'm searching roles in your market for you.",
    etaSec: 8,
  },
  "Scoring this role…": {
    spoken: "Let me score this role for you.",
    etaSec: 5,
  },
  "I'm checking the fit for this role…": {
    spoken: "Let me score this role for you.",
    etaSec: 5,
  },
  "Preparing your application kit…": {
    spoken: "I'm preparing your application kit.",
    etaSec: 10,
  },
  "I'm building your apply kit…": {
    spoken: "I'm preparing your application kit.",
    etaSec: 10,
  },
  "Updating your profile…": {
    spoken: "I'm updating your profile.",
    etaSec: 3,
  },
  "I'm updating your profile…": {
    spoken: "I'm updating your profile.",
    etaSec: 3,
  },
  "Thinking…": {
    spoken: "One moment.",
    etaSec: 3,
  },
};

export function spokenFillerForStatus(status: string): string | null {
  return STATUS_META[status]?.spoken ?? null;
}

export function etaSecForStatus(status: string): number | null {
  return STATUS_META[status]?.etaSec ?? null;
}

export function formatStatusWithEta(status: string, etaSec?: number | null): string {
  const eta = etaSec ?? etaSecForStatus(status);
  if (!eta) return status;
  return `${status.replace(/…$/, "")} (~${eta}s)…`;
}
