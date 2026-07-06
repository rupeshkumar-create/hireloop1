import type { MatchedJob } from "@/lib/api/matches";

/** Shared chat message shape across Aarya, Nitya, and public portfolio. */
export type ChatRole = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  created_at?: string;
  content_type?: "text" | "voice";
  jobs?: MatchedJob[];
};

export type ChatChip = {
  id: string;
  label: string;
  message: string;
};

export type ChatStreamPayload = {
  text?: string;
  status?: string;
  error?: string;
  chips?: ChatChip[];
  jobs?: MatchedJob[];
  spoken_filler?: string;
  eta_sec?: number;
  hinglish_hint?: boolean;
};

export type ChatStreamCallbacks = {
  onText?: (chunk: string, accumulated: string) => void;
  onStatus?: (status: string) => void;
  onChips?: (chips: ChatChip[]) => void;
  onJobs?: (jobs: MatchedJob[]) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
};
