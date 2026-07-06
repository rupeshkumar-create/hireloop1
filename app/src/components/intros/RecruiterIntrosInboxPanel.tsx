"use client";

/**
 * Recruiter inbox — master/detail: intro list + live recruiter↔candidate chat.
 */

import { useEffect, useMemo, useState } from "react";
import { Clock, MessageCircle, XCircle } from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import { IntroChat } from "@/components/intros/IntroChat";
import { Badge, Button, EmptyState, useToast } from "@/components/ui";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

export type RecruiterInboxItem = {
  id: string;
  status: string;
  direction?: string;
  job_title: string;
  candidate_name?: string;
  role_title?: string | null;
  updated_at: string;
};

const STATUS_META: Record<
  string,
  { tone: "muted" | "strong" | "accent"; label: string }
> = {
  pending: { tone: "accent", label: "Needs response" },
  invited: { tone: "muted", label: "Invited" },
  recruiter_notified: { tone: "accent", label: "Notified" },
  draft_ready: { tone: "accent", label: "Draft ready" },
  sent: { tone: "strong", label: "Email sent" },
  accepted: { tone: "strong", label: "Accepted" },
  declined: { tone: "muted", label: "Declined" },
  expired: { tone: "muted", label: "Expired" },
};

type ListGroup = {
  id: string;
  label: string;
  items: RecruiterInboxItem[];
};

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function groupItems(items: RecruiterInboxItem[]): ListGroup[] {
  const visible = items.filter(
    (item) =>
      !(
        item.direction === "candidate_to_hm" &&
        ["draft_ready", "sent"].includes(item.status)
      ),
  );
  const needsAction = visible.filter(
    (item) =>
      item.direction === "candidate_to_recruiter" && item.status === "pending",
  );
  const inProgress = visible.filter(
    (item) =>
      item.status === "accepted" ||
      (item.direction === "recruiter_to_candidate" &&
        ["pending", "invited"].includes(item.status)),
  );
  const other = visible.filter(
    (item) => !needsAction.includes(item) && !inProgress.includes(item),
  );

  const groups: ListGroup[] = [];
  if (needsAction.length) {
    groups.push({ id: "action", label: "Needs your response", items: needsAction });
  }
  if (inProgress.length) {
    groups.push({ id: "progress", label: "In progress", items: inProgress });
  }
  if (other.length) {
    groups.push({ id: "other", label: "All intro activity", items: other });
  }
  return groups;
}

export function RecruiterIntrosInboxPanel({
  items,
  loading,
  onItemsChange,
}: {
  items: RecruiterInboxItem[];
  loading?: boolean;
  onItemsChange?: (items: RecruiterInboxItem[]) => void;
}) {
  const { toast } = useToast();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [responding, setResponding] = useState<string | null>(null);

  const groups = useMemo(() => groupItems(items), [items]);
  const flatItems = useMemo(() => groups.flatMap((g) => g.items), [groups]);

  useEffect(() => {
    setSelectedId((prev) => {
      if (prev && flatItems.some((i) => i.id === prev)) return prev;
      const chatReady = flatItems.find((i) => i.status === "accepted");
      const needsYou = flatItems.find(
        (i) => i.direction === "candidate_to_recruiter" && i.status === "pending",
      );
      return chatReady?.id ?? needsYou?.id ?? flatItems[0]?.id ?? null;
    });
  }, [flatItems]);

  async function respond(introId: string, accept: boolean) {
    setResponding(introId);
    try {
      await apiFetch(`/api/v1/recruiter/intros/${introId}/respond?accept=${accept}`, {
        method: "POST",
      });
      const next = items.map((i) =>
        i.id === introId ? { ...i, status: accept ? "accepted" : "declined" } : i,
      );
      onItemsChange?.(next);
      if (accept) setSelectedId(introId);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setResponding(null);
    }
  }

  const selected = flatItems.find((i) => i.id === selectedId) ?? null;
  const selectedMeta = selected
    ? (STATUS_META[selected.status] ?? {
        tone: "muted" as const,
        label: selected.status,
      })
    : null;
  const fromCandidate = selected?.direction === "candidate_to_recruiter";
  const canRespond = fromCandidate && selected?.status === "pending";
  const canChat = selected?.status === "accepted";

  if (loading) {
    return (
      <div className="flex h-full min-h-[360px]">
        <div className="w-full max-w-xs border-r border-ink-100 p-3 space-y-2">
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

  if (flatItems.length === 0) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center p-6">
        <EmptyState
          icon={<MessageCircle strokeWidth={1.5} />}
          title="No intro activity yet"
          description="When candidates request intros to your roles, they'll appear here. Accept to open a direct chat."
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Thread list */}
      <div className="w-full max-w-[300px] shrink-0 border-r border-ink-100 overflow-y-auto bg-paper-1">
        {groups.map((group) => (
          <div key={group.id}>
            <p className="sticky top-0 z-10 bg-paper-1 px-4 py-2 text-micro font-medium uppercase tracking-wide text-ink-400 border-b border-ink-100">
              {group.label}
            </p>
            <ul className="divide-y divide-ink-100">
              {group.items.map((item) => {
                const meta = STATUS_META[item.status] ?? {
                  tone: "muted" as const,
                  label: item.status,
                };
                const active = item.id === selectedId;
                const title = item.role_title ?? item.job_title;

                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className={cn(
                        "w-full text-left px-4 py-3 transition-colors",
                        active ? "bg-ink-50 border-l-2 border-l-accent" : "hover:bg-ink-50/60 border-l-2 border-l-transparent",
                      )}
                    >
                      <p className="text-small font-medium text-ink-900 truncate">
                        {item.candidate_name ?? "Candidate"}
                      </p>
                      <p className="text-micro text-ink-500 truncate mt-0.5">{title}</p>
                      <div className="flex items-center justify-between gap-2 mt-1.5">
                        <Badge tone={meta.tone} className="text-[10px]">
                          {meta.label}
                        </Badge>
                        <span className="text-[10px] text-ink-400 shrink-0">
                          {timeAgo(item.updated_at)}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {/* Selected thread */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0 bg-paper-0">
        {selected ? (
          <>
            <div className="shrink-0 px-4 py-3 border-b border-ink-100">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-small font-semibold text-ink-900 truncate">
                    {selected.candidate_name ?? "Candidate"}
                    {fromCandidate ? " · intro request" : ""}
                  </p>
                  <p className="text-micro text-ink-500 truncate mt-0.5">
                    {selected.role_title ?? selected.job_title}
                  </p>
                </div>
                {selectedMeta && (
                  <Badge tone={selectedMeta.tone} className="shrink-0">
                    {selectedMeta.label}
                  </Badge>
                )}
              </div>

              {canRespond && (
                <div className="flex items-center gap-2 mt-3">
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
                </div>
              )}
            </div>

            <div className="flex-1 min-h-0 flex flex-col p-3">
              {canChat ? (
                <IntroChat introId={selected.id} side="recruiter" fillHeight />
              ) : selected.status === "declined" ? (
                <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
                  <XCircle className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
                  <p className="text-small font-medium text-ink-800">Intro declined</p>
                </div>
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
                  <Clock className="h-8 w-8 text-ink-300 mb-3" strokeWidth={1.5} />
                  <p className="text-small font-medium text-ink-800">
                    {canRespond ? "Accept to open chat" : "Waiting for a response"}
                  </p>
                  <p className="text-micro text-ink-500 mt-1 max-w-xs">
                    Direct messaging opens once the intro is accepted.
                  </p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-micro text-ink-400">
            Select a conversation
          </div>
        )}
      </div>
    </div>
  );
}

/** Live refetch hook for parent pages. */
export function useRecruiterInboxRealtime(onChange: () => void) {
  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("intro_requests:recruiter_panel")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "intro_requests" },
        () => {
          onChange();
        },
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [onChange]);
}
