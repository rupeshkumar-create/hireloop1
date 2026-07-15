import { apiFetch } from "@/lib/api/client";

/** Fired on `window` after Google OAuth succeeds so UI can refresh connected state. */
export const GOOGLE_CONNECTED_EVENT = "hireschema:google-connected";

/** Google connection state for the current candidate. */
export type GoogleStatus = {
  connected: boolean;
  gmail_email: string | null;
  /** gmail.send granted — powers HM intro outreach (P13). */
  send_enabled: boolean;
  /** calendar.events granted — powers voice-session booking + Meet links (P07). */
  calendar_enabled: boolean;
};

export async function fetchGoogleStatus(): Promise<GoogleStatus> {
  return apiFetch<GoogleStatus>("/api/v1/gmail/status");
}

/**
 * Begin the Google OAuth flow. The connect endpoint needs the Bearer token, so
 * we fetch the consent URL as JSON and then navigate the top window to it.
 */
export async function startGoogleConnect(): Promise<void> {
  const { auth_url } = await apiFetch<{ auth_url: string }>("/api/v1/gmail/auth-url");
  window.location.href = auth_url;
}

export async function disconnectGoogle(): Promise<void> {
  await apiFetch("/api/v1/gmail/disconnect", { method: "DELETE" });
}
