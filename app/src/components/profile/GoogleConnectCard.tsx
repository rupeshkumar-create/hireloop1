"use client";

import { useEffect, useState } from "react";
import { Check } from "@/components/brand/icons";
import { Button, useToast } from "@/components/ui";
import {
  disconnectGoogle,
  fetchGoogleStatus,
  GOOGLE_CONNECTED_EVENT,
  startGoogleConnect,
  type GoogleStatus,
} from "@/lib/api/gmail";

/**
 * Optional Google connect row for profile Overview.
 * One consent: gmail.send + calendar.events.
 */
export function GoogleConnectCard() {
  const { toast } = useToast();
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setStatus(await fetchGoogleStatus());
    } catch {
      /* leave previous state */
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    const onConnected = (ev: Event) => {
      const detail = (ev as CustomEvent<GoogleStatus>).detail;
      if (detail) setStatus(detail);
      else void refresh();
      setLoading(false);
    };
    window.addEventListener(GOOGLE_CONNECTED_EVENT, onConnected);
    return () => window.removeEventListener(GOOGLE_CONNECTED_EVENT, onConnected);
  }, []);

  async function handleConnect() {
    setBusy(true);
    try {
      await startGoogleConnect();
    } catch (e) {
      setBusy(false);
      toast.error(e instanceof Error ? e.message : "Couldn't start Google sign-in");
    }
  }

  async function handleDisconnect() {
    setBusy(true);
    try {
      await disconnectGoogle();
      await refresh();
      toast.success("Google disconnected");
    } catch {
      toast.error("Couldn't disconnect");
    } finally {
      setBusy(false);
    }
  }

  const connected = status?.connected ?? false;
  const calendarMissing = connected && !status?.calendar_enabled;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-ink-100 bg-paper-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-small font-medium text-ink-900">Google</p>
        <p className="text-micro text-ink-500">
          {connected
            ? "Intros and follow-ups send from your Gmail. We never read your inbox."
            : "Connect so Aarya can send approved intros from your Gmail and add Meet links for booked calls."}
        </p>
        {loading ? (
          <p className="mt-1 text-micro text-ink-400">Checking…</p>
        ) : connected ? (
          <p className="mt-1 flex items-center gap-1.5 text-micro text-ink-700">
            <Check className="h-3.5 w-3.5" strokeWidth={2} />
            Connected{status?.gmail_email ? ` as ${status.gmail_email}` : ""}
            {calendarMissing ? " · reconnect for Calendar" : ""}
          </p>
        ) : (
          <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-micro text-ink-500">
            <li>Warm intros from your own email address</li>
            <li>Approve-first follow-ups in the same thread</li>
            <li>Optional Meet links when you book with Aarya</li>
          </ul>
        )}
      </div>
      <div className="flex shrink-0 gap-2">
        {loading ? null : connected ? (
          <>
            {calendarMissing && (
              <Button variant="secondary" size="sm" loading={busy} onClick={() => void handleConnect()}>
                Reconnect
              </Button>
            )}
            <Button variant="ghost" size="sm" loading={busy} onClick={() => void handleDisconnect()}>
              Disconnect
            </Button>
          </>
        ) : (
          <Button variant="secondary" size="sm" loading={busy} onClick={() => void handleConnect()}>
            Connect
          </Button>
        )}
      </div>
    </div>
  );
}
