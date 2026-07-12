"use client";

import { useEffect, useState } from "react";
import { Check } from "@/components/brand/icons";
import { Button, useToast } from "@/components/ui";
import {
  disconnectGoogle,
  fetchGoogleStatus,
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
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("gmail") === "connected") {
        toast.success("Google connected");
        params.delete("gmail");
        const qs = params.toString();
        window.history.replaceState(
          {},
          "",
          window.location.pathname + (qs ? `?${qs}` : ""),
        );
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
          Optional — send intros from your Gmail and add Meet links for booked calls.
        </p>
        {loading ? (
          <p className="mt-1 text-micro text-ink-400">Checking…</p>
        ) : connected ? (
          <p className="mt-1 flex items-center gap-1.5 text-micro text-ink-700">
            <Check className="h-3.5 w-3.5" strokeWidth={2} />
            Connected{status?.gmail_email ? ` as ${status.gmail_email}` : ""}
            {calendarMissing ? " · reconnect for Calendar" : ""}
          </p>
        ) : null}
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
