"use client";

import { useEffect, useState } from "react";
import { Mail, Send } from "@/components/brand/icons";
import { GoogleConnectCard } from "@/components/profile/GoogleConnectCard";
import {
  approveIntroSend,
  fetchIntroDetail,
  invalidateIntrosCache,
  type IntroDetail,
} from "@/lib/api/intros";
import { Button, useToast } from "@/components/ui";

type DraftPayload = {
  subject?: string;
  body_html?: string;
  body_text?: string;
};

function parseDraft(raw: string | null | undefined): DraftPayload | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as DraftPayload;
  } catch {
    return null;
  }
}

export function IntroDraftPanel({
  introId,
  onSent,
}: {
  introId: string;
  onSent: () => void;
}) {
  const { toast } = useToast();
  const [detail, setDetail] = useState<IntroDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const load = async () => {
      try {
        const d = await fetchIntroDetail(introId);
        if (!cancelled) setDetail(d);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [introId]);

  async function handleSend() {
    if (!detail?.gmail_connected) {
      toast.error("Connect Google first so we can send from your Gmail.");
      return;
    }
    setSending(true);
    try {
      await approveIntroSend(introId);
      invalidateIntrosCache();
      toast.success("Intro email sent from your Gmail");
      onSent();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-small text-ink-400">Loading draft…</p>
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-small text-destructive bg-destructive-bg rounded-md px-4 py-3 m-4">
        {error}
      </p>
    );
  }

  const draft = parseDraft(detail?.draft_email);
  const inProgress = ["pending", "enriching", "drafting"].includes(detail?.status ?? "");

  if (inProgress && !draft) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
        <Mail className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
        <p className="text-small font-medium text-ink-800">Nitya is preparing your intro</p>
        <p className="text-micro text-ink-500 mt-1 max-w-sm">
          {detail?.status === "enriching"
            ? "Finding the hiring manager email via Apify, then verifying it…"
            : detail?.status === "drafting"
              ? "Drafting a personalised email from your profile…"
              : "Starting the intro campaign…"}
        </p>
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
        <p className="text-small text-ink-600">
          {detail?.error_message ?? "No draft available yet. Check back in a moment."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0 gap-4 p-4 overflow-y-auto">
      <div>
        <p className="text-micro font-medium uppercase tracking-wide text-ink-500">
          Intro campaign draft
        </p>
        <p className="text-small text-ink-500 mt-1">
          Review Nitya&apos;s email to{" "}
          <span className="text-ink-800 font-medium">{detail?.hm_name}</span>
          {detail?.hm_email ? ` (${detail.hm_email})` : ""}. It sends from your Gmail when you
          approve — never from Hireschema.
        </p>
      </div>

      {!detail?.gmail_connected && (
        <div className="space-y-2">
          <p className="text-micro text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            Connect Google to send this intro. Hireschema only uses send-only access — we never read
            your inbox.
          </p>
          <GoogleConnectCard />
        </div>
      )}

      <div className="rounded-lg border border-ink-100 bg-paper-1 overflow-hidden">
        <div className="px-4 py-2 border-b border-ink-100 bg-ink-50/50">
          <p className="text-micro text-ink-500">Subject</p>
          <p className="text-small font-medium text-ink-900">{draft.subject ?? "(no subject)"}</p>
        </div>
        <div
          className="px-4 py-3 text-small text-ink-800 leading-relaxed prose prose-sm max-w-none"
          dangerouslySetInnerHTML={{
            __html: draft.body_html ?? `<p>${draft.body_text ?? ""}</p>`,
          }}
        />
      </div>

      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="primary"
          size="sm"
          loading={sending}
          disabled={!detail?.gmail_connected}
          onClick={() => void handleSend()}
        >
          <Send className="h-4 w-4 mr-1.5" strokeWidth={1.5} />
          Send from my Gmail
        </Button>
        {detail?.gmail_connected && (
          <span className="text-micro text-ink-500">Gmail connected — ready to send</span>
        )}
      </div>
    </div>
  );
}
