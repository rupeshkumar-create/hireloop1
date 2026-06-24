/**
 * Direct intro chat client — candidate ↔ recruiter messaging on an accepted
 * intro. The same thread is reachable from either side; `side` selects the
 * auth-scoped base path.
 */

import { apiFetch } from "@/lib/api/client";

export type IntroChatSide = "candidate" | "recruiter";

export type IntroMessage = {
  id: string;
  sender_type: IntroChatSide;
  body: string;
  created_at: string;
  mine: boolean;
};

export type IntroThread = {
  intro_id: string;
  status: string;
  can_chat: boolean;
  you: IntroChatSide;
  messages: IntroMessage[];
};

function basePath(introId: string, side: IntroChatSide): string {
  return side === "recruiter"
    ? `/api/v1/recruiter/intros/${introId}/messages`
    : `/api/v1/intros/${introId}/messages`;
}

export async function fetchIntroThread(
  introId: string,
  side: IntroChatSide
): Promise<IntroThread> {
  return apiFetch<IntroThread>(basePath(introId, side));
}

export async function sendIntroMessage(
  introId: string,
  side: IntroChatSide,
  body: string
): Promise<IntroMessage> {
  return apiFetch<IntroMessage>(basePath(introId, side), {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}
