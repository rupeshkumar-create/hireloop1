"use client";

import { useEffect, useState } from "react";
import { Mail, Send } from "@/components/brand/icons";
import { GoogleConnectCard } from "@/components/profile/GoogleConnectCard";
import {
  approveFollowupSend,
  approveIntroSend,
  approveThankyouSend,
  createThankyouDraft,
  fetchIntroDetail,
  invalidateIntrosCache,
  patchFollowupDraft,
  patchThankyouDraft,
  type IntroDetail,
  type OutboundDraft,
} from "@/lib/api/intros";
import { Button, useToast } from "@/components/ui";

function parseDraft(raw: string | OutboundDraft | null | undefined): OutboundDraft | null {
  if (!raw) return null;
  if (typeof raw === "object") return raw;
  try {
    return JSON.parse(raw) as OutboundDraft;
  } catch {
    return null;
  }
}

function DraftEditor({
  title,
  subtitle,
  draft,
  gmailConnected,
  sending,
  onChangeBody,
  onSend,
  sendLabel,
}: {
  title: string;
  subtitle: string;
  draft: OutboundDraft;
  gmailConnected: boolean;
  sending: boolean;
  onChangeBody: (text: string) => void;
  onSend: () => void;
  sendLabel: string;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="text-micro font-medium uppercase tracking-wide text-ink-500">{title}</p>
        <p className="text-small text-ink-500 mt-1">{subtitle}</p>
      </div>

      {!gmailConnected && (
        <div className="space-y-2">
          <p className="text-micro text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            Connect Google to send from your Gmail. Send-only access — we never read your inbox.
          </p>
          <GoogleConnectCard />
        </div>
      )}

      <div className="rounded-lg border border-ink-100 bg-paper-1 overflow-hidden">
        <div className="px-4 py-2 border-b border-ink-100 bg-ink-50/50">
          <p className="text-micro text-ink-500">Subject</p>
          <p className="text-small font-medium text-ink-900">{draft.subject ?? "(no subject)"}</p>
        </div>
        <textarea
          className="w-full min-h-[140px] px-4 py-3 text-small text-ink-800 leading-relaxed bg-transparent resize-y focus:outline-none"
          value={draft.body_text ?? ""}
          onChange={(e) => onChangeBody(e.target.value)}
        />
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          size="sm"
          loading={sending}
          disabled={!gmailConnected}
          onClick={onSend}
        >
          <Send className="h-4 w-4 mr-1.5" strokeWidth={1.5} />
          {sendLabel}
        </Button>
      </div>
    </div>
  );
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
  const [followupDraft, setFollowupDraft] = useState<OutboundDraft | null>(null);
  const [thankyouDraft, setThankyouDraft] = useState<OutboundDraft | null>(null);

  async function load() {
    const d = await fetchIntroDetail(introId);
    setDetail(d);
    setFollowupDraft(parseDraft(d.followup_draft_email));
    setThankyouDraft(parseDraft(d.thankyou_draft_email));
    return d;
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const run = async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    const interval = window.setInterval(() => {
      void load().catch(() => undefined);
    }, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on intro change only
  }, [introId]);

  async function handleIntroSend() {
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

  async function handleFollowupSend() {
    if (!detail?.gmail_connected) {
      toast.error("Connect Google first so we can send from your Gmail.");
      return;
    }
    setSending(true);
    try {
      if (followupDraft?.body_text) {
        await patchFollowupDraft(introId, { body_text: followupDraft.body_text });
      }
      await approveFollowupSend(introId);
      invalidateIntrosCache();
      toast.success("Follow-up sent in the same Gmail thread");
      await load();
      onSent();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  async function handleThankyouCreate() {
    setSending(true);
    try {
      const draft = await createThankyouDraft(introId);
      setThankyouDraft(draft);
      invalidateIntrosCache();
      toast.success("Thank-you draft ready — edit and approve below");
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  async function handleThankyouSend() {
    if (!detail?.gmail_connected) {
      toast.error("Connect Google first so we can send from your Gmail.");
      return;
    }
    setSending(true);
    try {
      if (thankyouDraft?.body_text) {
        await patchThankyouDraft(introId, {
          subject: thankyouDraft.subject,
          body_text: thankyouDraft.body_text,
        });
      }
      await approveThankyouSend(introId);
      invalidateIntrosCache();
      toast.success("Thank-you sent from your Gmail");
      await load();
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

  const introDraft = parseDraft(detail?.draft_email);
  const inProgress = ["pending", "enriching", "drafting"].includes(detail?.status ?? "");
  const showIntroDraft =
    Boolean(introDraft) && ["draft_ready", "drafting", "pending", "enriching"].includes(detail?.status ?? "");
  const followupReady = Boolean(followupDraft) && !detail?.nudged_at;
  const thankyouReady = Boolean(thankyouDraft) && !detail?.thankyou_sent_at;
  const canMakeThankyou =
    ["sent", "opened", "replied", "accepted"].includes(detail?.status ?? "") &&
    !detail?.thankyou_sent_at &&
    !thankyouReady;

  if (inProgress && !introDraft && !followupReady && !thankyouReady) {
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

  return (
    <div className="flex flex-1 flex-col min-h-0 gap-6 p-4 overflow-y-auto">
      {showIntroDraft && introDraft && (
        <div className="flex flex-col gap-3">
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
                Connect Google to send this intro. Send-only access — we never read your inbox.
              </p>
              <GoogleConnectCard />
            </div>
          )}
          <div className="rounded-lg border border-ink-100 bg-paper-1 overflow-hidden">
            <div className="px-4 py-2 border-b border-ink-100 bg-ink-50/50">
              <p className="text-micro text-ink-500">Subject</p>
              <p className="text-small font-medium text-ink-900">
                {introDraft.subject ?? "(no subject)"}
              </p>
            </div>
            <div
              className="px-4 py-3 text-small text-ink-800 leading-relaxed prose prose-sm max-w-none"
              dangerouslySetInnerHTML={{
                __html: introDraft.body_html ?? `<p>${introDraft.body_text ?? ""}</p>`,
              }}
            />
          </div>
          <Button
            variant="primary"
            size="sm"
            loading={sending}
            disabled={!detail?.gmail_connected}
            onClick={() => void handleIntroSend()}
          >
            <Send className="h-4 w-4 mr-1.5" strokeWidth={1.5} />
            Send from my Gmail
          </Button>
        </div>
      )}

      {followupReady && followupDraft && (
        <DraftEditor
          title="Follow-up ready"
          subtitle="No reply yet — this polite bump stays in the same Gmail thread. Edit, then approve."
          draft={followupDraft}
          gmailConnected={Boolean(detail?.gmail_connected)}
          sending={sending}
          onChangeBody={(text) => setFollowupDraft((d) => ({ ...(d ?? {}), body_text: text }))}
          onSend={() => void handleFollowupSend()}
          sendLabel="Send follow-up"
        />
      )}

      {thankyouReady && thankyouDraft && (
        <DraftEditor
          title="Thank-you draft"
          subtitle="Short thank-you from your Gmail. Prefer the same thread when available."
          draft={thankyouDraft}
          gmailConnected={Boolean(detail?.gmail_connected)}
          sending={sending}
          onChangeBody={(text) => setThankyouDraft((d) => ({ ...(d ?? {}), body_text: text }))}
          onSend={() => void handleThankyouSend()}
          sendLabel="Send thank-you"
        />
      )}

      {canMakeThankyou && (
        <div className="rounded-lg border border-ink-100 bg-ink-50/40 px-4 py-3">
          <p className="text-small font-medium text-ink-800">Send a thank-you?</p>
          <p className="text-micro text-ink-500 mt-1">
            Draft a short note to {detail?.hm_name ?? "the hiring manager"} — you approve before it
            sends.
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            loading={sending}
            onClick={() => void handleThankyouCreate()}
          >
            Draft thank-you
          </Button>
        </div>
      )}

      {!showIntroDraft && !followupReady && !thankyouReady && !canMakeThankyou && (
        <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
          <p className="text-small text-ink-600">
            {detail?.error_message ??
              (detail?.nudged_at
                ? "Follow-up already sent. We'll keep watching this intro."
                : detail?.thankyou_sent_at
                  ? "Thank-you already sent."
                  : "No outbound draft right now.")}
          </p>
        </div>
      )}
    </div>
  );
}
