"use client";

/**
 * Dashboard inbox — master/detail: intro list + live candidate↔recruiter chat.
 */

import { useEffect, useState } from "react";
import {
  Building2,
  Clock,
  MessageCircle,
  XCircle,
} from "@/components/brand/icons";
import {
  cancelIntro,
  fetchIntros,
  getCachedIntros,
  respondToIntro,
  type IntroRequest,
} from "@/lib/api/intros";
import { sanitizeDisplayName } from "@/lib/auth/display-name";
import { IntroChat } from "@/components/intros/IntroChat";
import { IntroDraftPanel } from "@/components/intros/IntroDraftPanel";
import { Badge, Button, EmptyState, useToast } from "@/components/ui";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const STATUS_META: Record<
  string,
  { tone: "muted" | "strong" | "accent"; label: string }
> = {
  pending: { tone: "muted", label: "Pending" },
  invited: { tone: "accent", label: "Invite sent" },
  recruiter_notified: { tone: "accent", label: "Notified" },
  enriching: { tone: "accent", label: "Finding contact" },
  drafting: { tone: "accent", label: "Drafting email" },
  draft_ready: { tone: "accent", label: "Draft ready" },
  sent: { tone: "strong", label: "Intro sent" },
  accepted: { tone: "strong", label: "Accepted" },
  declined: { tone: "muted", label: "Declined" },
  expired: { tone: "muted", label: "Expired" },
  cancelled: { tone: "muted", label: "Cancelled" },
};

function contactLabel(intro: IntroRequest): string | null {
  const name = sanitizeDisplayName(intro.hm_name);
  if (!name) return null;
  if (intro.direction === "recruiter_to_candidate") {
    return name;
  }
  return name;
}

export function IntrosInboxPanel() {
  const { toast } = useToast();
  const cached = getCachedIntros();
  const [intros, setIntros] = useState<IntroRequest[]>(cached ?? []);
  const [loading, setLoading] = useState(cached === null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [responding, setResponding] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const data = await fetchIntros({ force: true });
      setIntros(data);
      setSelectedId((prev) => {
        if (prev && data.some((i) => i.id === prev)) return prev;
        const chatReady = data.find((i) => i.status === "accepted");
        return chatReady?.id ?? data[0]?.id ?? null;
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const supabase = createClient();
    let channel: ReturnType<typeof supabase.channel> | null = null;
    let cancelled = false;

    async function subscribe() {
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;
      if (token) await supabase.realtime.setAuth(token);
      if (cancelled) return;
      channel = supabase
        .channel("intro_requests:inbox_panel")
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "intro_requests" },
          () => {
            void load();
          },
        )
        .subscribe();
    }

    void subscribe();
    return () => {
      cancelled = true;
      if (channel) void supabase.removeChannel(channel);
    };
  }, []);

  async function cancel(introId: string) {
    setCancelling(introId);
    try {
      await cancelIntro(introId);
      setIntros((prev) =>
        prev.map((i) => (i.id === introId ? { ...i, status: "cancelled" } : i)),
      );
      toast.success("Intro request cancelled");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setCancelling(null);
    }
  }

  async function respond(introId: string, accept: boolean) {
    setResponding(introId);
    try {
      await respondToIntro(introId, accept);
      setIntros((prev) =>
        prev.map((i) =>
          i.id === introId
            ? { ...i, status: accept ? "accepted" : "declined" }
            : i,
        ),
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setResponding(null);
    }
  }

  const selected = intros.find((i) => i.id === selectedId) ?? null;
  const selectedMeta = selected
    ? (STATUS_META[selected.status] ?? { tone: "muted" as const, label: selected.status })
    : null;

  if (loading) {
    return (
      <div className="flex h-full min-h-[320px]">
        <div className="w-full max-w-[240px] border-r border-ink-100 p-3 space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 rounded-lg bg-ink-100 animate-skeleton" />
          ))}
        </div>
        <div className="flex-1 p-4">
          <div className="h-full rounded-lg bg-ink-100 animate-skeleton" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3 m-5">
        {error}
      </p>
    );
  }

  if (intros.length === 0) {
    return (
      <div className="p-5">
        <EmptyState
          icon={<Building2 strokeWidth={1.5} />}
          title="No intro requests yet"
          description="Ask Aarya to request an intro for a role you like. Once accepted, you can chat with the recruiter here."
        />
      </div>
    );
  }

  const fromRecruiter =
    selected?.direction === "recruiter_to_candidate";
  const isHmEmailIntro = selected?.direction === "candidate_to_hm";
  const canRespond = fromRecruiter && selected?.status === "pending";
  const canCancel =
    selected &&
    !fromRecruiter &&
    ["pending", "invited", "recruiter_notified", "enriching", "drafting", "draft_ready"].includes(
      selected.status,
    );
  const canChat = selected?.status === "accepted";
  const showDraftPanel =
    isHmEmailIntro &&
    ["pending", "enriching", "drafting", "draft_ready"].includes(selected?.status ?? "");

  return (
    <div className="flex h-full min-h-0">
      <div className="w-full max-w-[240px] shrink-0 border-r border-ink-100 overflow-y-auto">
        <ul className="divide-y divide-ink-100">
          {intros.map((intro) => {
            const meta = STATUS_META[intro.status] ?? {
              tone: "muted" as const,
              label: intro.status,
            };
            const active = intro.id === selectedId;
            const contact = contactLabel(intro);

            return (
              <li key={intro.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(intro.id)}
                  className={cn(
                    "w-full text-left px-4 py-3 transition-colors",
                    active ? "bg-ink-50" : "hover:bg-ink-50/60",
                  )}
                >
                  <p className="text-small font-medium text-ink-900 truncate">
                    {intro.job_title}
                  </p>
                  {intro.company_name && (
                    <p className="text-micro text-ink-500 truncate mt-0.5">
                      {intro.company_name}
                    </p>
                  )}
                  {contact && (
                    <p className="text-micro text-ink-400 truncate mt-0.5">
                      {contact}
                    </p>
                  )}
                  <div className="mt-1.5">
                    <Badge tone={meta.tone} className="text-[10px]">
                      {meta.label}
                    </Badge>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex-1 min-w-0 flex flex-col min-h-0 bg-paper-0">
        {selected ? (
          <>
            <div className="shrink-0 px-4 py-3 border-b border-ink-100">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-small font-semibold text-ink-900 truncate">
                    {selected.job_title}
                  </p>
                  <p className="text-micro text-ink-500 truncate">
                    {[selected.company_name, contactLabel(selected)]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                {selectedMeta && (
                  <Badge tone={selectedMeta.tone} className="shrink-0">
                    {selectedMeta.label}
                  </Badge>
                )}
              </div>

              {(canRespond || canCancel) && (
                <div className="flex items-center gap-2 mt-3">
                  {canRespond && (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void respond(selected.id, false)}
                        disabled={responding === selected.id}
                      >
                        Decline
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => void respond(selected.id, true)}
                        loading={responding === selected.id}
                      >
                        Accept & chat
                      </Button>
                    </>
                  )}
                  {canCancel && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void cancel(selected.id)}
                      loading={cancelling === selected.id}
                    >
                      Cancel request
                    </Button>
                  )}
                </div>
              )}
            </div>

            <div className="flex-1 min-h-0 flex flex-col p-3">
              {showDraftPanel && selected ? (
                <IntroDraftPanel
                  introId={selected.id}
                  onSent={() => {
                    setIntros((prev) =>
                      prev.map((i) =>
                        i.id === selected.id ? { ...i, status: "sent" } : i,
                      ),
                    );
                  }}
                />
              ) : canChat ? (
                <IntroChat introId={selected.id} side="candidate" fillHeight />
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
                  {selected.status === "sent" && isHmEmailIntro ? (
                    <>
                      <Clock className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
                      <p className="text-small font-medium text-ink-800">Intro email sent</p>
                      <p className="text-micro text-ink-500 mt-1 max-w-xs">
                        Your email went out from your Gmail. We&apos;ll update you if they reply.
                      </p>
                    </>
                  ) : selected.status === "pending" || selected.status === "sent" ? (
                    <>
                      <Clock className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
                      <p className="text-small font-medium text-ink-800">
                        Waiting for a response
                      </p>
                      <p className="text-micro text-ink-500 mt-1 max-w-xs">
                        Chat opens once the recruiter accepts your intro request.
                      </p>
                    </>
                  ) : selected.status === "declined" ? (
                    <>
                      <XCircle className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
                      <p className="text-small font-medium text-ink-800">Intro declined</p>
                    </>
                  ) : (
                    <>
                      <MessageCircle className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
                      <p className="text-small font-medium text-ink-800">
                        Chat not available for this status
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-micro text-ink-400">
            Select an intro to view details
          </div>
        )}
      </div>
    </div>
  );
}
