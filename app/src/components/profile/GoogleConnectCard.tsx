"use client";

import { useEffect, useState } from "react";
import { Calendar, Check, Mail } from "lucide-react";

import { Badge, Button, Card, CardBody, CardHeader, useToast } from "@/components/ui";
import {
  disconnectGoogle,
  fetchGoogleStatus,
  startGoogleConnect,
  type GoogleStatus,
} from "@/lib/api/gmail";

/**
 * Connect-Google card for the profile Overview tab. One consent grants:
 *   • gmail.send       → Aarya sends HM intros from the candidate's own Gmail (P13)
 *   • calendar.events  → voice-session bookings get a real Calendar event + Meet (P07)
 * Optional: nothing breaks if the candidate skips it (in-app intros + slots still work).
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
      /* leave previous state; the card just shows the connect CTA */
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // Surface the post-OAuth redirect (?gmail=connected) once, then clean the URL.
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("gmail") === "connected") {
        toast.success("Google connected");
        params.delete("gmail");
        const qs = params.toString();
        window.history.replaceState(
          {},
          "",
          window.location.pathname + (qs ? `?${qs}` : "")
        );
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleConnect() {
    setBusy(true);
    try {
      await startGoogleConnect(); // navigates away on success
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
    <Card>
      <CardHeader
        title="Connect Google"
        description="Optional. Lets Aarya send intros from your own Gmail and add a Google Meet link when you book a call. Send-only — Hireloop never reads your mail or calendar."
      />
      <CardBody className="!pt-0 space-y-3">
        {loading ? (
          <p className="text-small text-ink-400">Checking connection…</p>
        ) : connected ? (
          <>
            <div className="flex items-center gap-2 text-small text-ink-700">
              <Check className="h-4 w-4 text-ink-900" strokeWidth={2} />
              Connected{status?.gmail_email ? ` as ${status.gmail_email}` : ""}
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge tone={status?.send_enabled ? "strong" : "muted"}>
                <Mail className="h-3 w-3" strokeWidth={1.5} />
                {status?.send_enabled ? "Intro emails on" : "Intro emails off"}
              </Badge>
              <Badge tone={status?.calendar_enabled ? "strong" : "muted"}>
                <Calendar className="h-3 w-3" strokeWidth={1.5} />
                {status?.calendar_enabled ? "Calendar on" : "Calendar off"}
              </Badge>
            </div>
            {calendarMissing && (
              <p className="text-micro text-ink-500">
                Reconnect to enable calendar invites + Meet links for booked calls.
              </p>
            )}
            <div className="flex gap-2">
              {calendarMissing && (
                <Button variant="primary" size="sm" loading={busy} onClick={() => void handleConnect()}>
                  Reconnect
                </Button>
              )}
              <Button variant="ghost" size="sm" loading={busy} onClick={() => void handleDisconnect()}>
                Disconnect
              </Button>
            </div>
          </>
        ) : (
          <Button variant="primary" size="sm" loading={busy} onClick={() => void handleConnect()}>
            Connect Google
          </Button>
        )}
      </CardBody>
    </Card>
  );
}
