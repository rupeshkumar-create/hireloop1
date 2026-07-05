"use client";

/**
 * Recruiter inbox — P18
 * Cross-role activity: roles list + recent intro events.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Briefcase,
  ChevronRight,
  Clock,
  Inbox,
  Plus,
  RefreshCw,
} from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import { Badge, Button, Card, CardBody, EmptyState, useToast } from "@/components/ui";
import { IntroChat } from "@/components/intros/IntroChat";
import { RecruiterBreadcrumbs } from "@/components/ux";
import { createClient } from "@/lib/supabase/client";

type InboxItem = {
  id: string;
  status: string;
  direction?: string;
  job_title: string;
  candidate_name?: string;
  role_title?: string | null;
  updated_at: string;
};

type RoleRow = {
  id: string;
  title: string;
  status: string;
  pipeline_count: number;
};

type InboxData = {
  items: InboxItem[];
  roles: RoleRow[];
};

const INTRO_STATUS_BADGE: Record<string, { tone: "muted" | "strong" | "accent"; label: string }> = {
  pending:           { tone: "accent",  label: "Needs response"  },
  invited:           { tone: "muted",   label: "Invited"         },
  recruiter_notified:{ tone: "accent",  label: "Notified"        },
  draft_ready:       { tone: "accent",  label: "Draft ready"     },
  sent:              { tone: "strong",  label: "Email sent"      },
  accepted:          { tone: "strong",  label: "Accepted ✓"      },
  declined:          { tone: "muted",   label: "Declined"        },
  expired:           { tone: "muted",   label: "Expired"         },
};

const ROLE_STATUS_BADGE: Record<string, { tone: "muted" | "strong" | "accent" }> = {
  active:   { tone: "accent" },
  paused:   { tone: "muted"  },
  closed:   { tone: "muted"  },
  draft:    { tone: "muted"  },
};

export default function RecruiterInboxPage() {
  const { toast } = useToast();
  const [data, setData]       = useState<InboxData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [responding, setResponding] = useState<string | null>(null);
  const [openChat, setOpenChat] = useState<Set<string>>(new Set());

  async function respond(introId: string, accept: boolean) {
    setResponding(introId);
    try {
      await apiFetch(`/api/v1/recruiter/intros/${introId}/respond?accept=${accept}`, {
        method: "POST",
      });
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.map((i) =>
                i.id === introId
                  ? { ...i, status: accept ? "accepted" : "declined" }
                  : i
              ),
            }
          : prev
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setResponding(null);
    }
  }

  function toggleChat(introId: string) {
    setOpenChat((prev) => {
      const next = new Set(prev);
      if (next.has(introId)) next.delete(introId);
      else next.add(introId);
      return next;
    });
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const d = await apiFetch<InboxData>("/api/v1/recruiter/inbox");
      setData(d);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  // Live: refetch when any of this recruiter's intros change (RLS scopes
  // delivery). Reflects new candidate requests + accept/decline instantly.
  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("intro_requests:recruiter")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "intro_requests" },
        () => { void load(); }
      )
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, []);

  function timeAgo(iso: string) {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  const items = (data?.items ?? []).filter(
    (item) =>
      !(
        item.direction === "candidate_to_hm" &&
        ["draft_ready", "sent"].includes(item.status)
      )
  );
  const needsAction = items.filter(
    (item) =>
      item.direction === "candidate_to_recruiter" && item.status === "pending"
  );
  const inProgress = items.filter(
    (item) =>
      item.status === "accepted" ||
      (item.direction === "recruiter_to_candidate" &&
        ["pending", "invited"].includes(item.status))
  );
  const other = items.filter(
    (item) => !needsAction.includes(item) && !inProgress.includes(item)
  );

  function renderIntroItem(item: InboxItem) {
    const meta = INTRO_STATUS_BADGE[item.status] ?? {
      tone: "muted" as const,
      label: item.status,
    };
    const fromCandidate = item.direction === "candidate_to_recruiter";
    const canRespond = fromCandidate && item.status === "pending";
    const canChat = item.status === "accepted";
    const chatOpen = openChat.has(item.id);
    return (
      <div
        key={item.id}
        className="rounded-lg border border-ink-100 bg-paper-1 px-4 py-3"
      >
        <div className="flex items-center gap-3">
          <Clock className="h-4 w-4 text-ink-300 shrink-0" strokeWidth={1.5} />
          <div className="flex-1 min-w-0">
            <p className="text-small text-ink-900 truncate">
              {item.candidate_name && (
                <span className="font-medium">
                  {item.candidate_name}
                  {fromCandidate ? " wants an intro · " : " → "}
                </span>
              )}
              {item.role_title ?? item.job_title}
            </p>
          </div>
          <Badge tone={meta.tone}>{meta.label}</Badge>
          <span className="text-micro text-ink-300 shrink-0">
            {timeAgo(item.updated_at)}
          </span>
        </div>

        {(canRespond || canChat) && (
          <div className="flex items-center justify-end gap-2 mt-2">
            {canRespond && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void respond(item.id, false)}
                  disabled={responding === item.id}
                >
                  Decline
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void respond(item.id, true)}
                  loading={responding === item.id}
                >
                  Accept
                </Button>
              </>
            )}
            {canChat && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => toggleChat(item.id)}
              >
                {chatOpen ? "Hide chat" : "Open chat"}
              </Button>
            )}
          </div>
        )}

        {canChat && chatOpen && (
          <IntroChat introId={item.id} side="recruiter" />
        )}
      </div>
    );
  }

  return (
    <div className="px-4 md:px-6 py-6 space-y-8 max-w-3xl mx-auto">
        <RecruiterBreadcrumbs crumbs={[{ label: "Inbox" }]} />

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-h2 font-semibold text-ink-900">Inbox</h1>
            <p className="text-small text-ink-500 mt-0.5">
              Roles, intros, and candidate activity
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void load()}
              loading={loading}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
            >
              Refresh
            </Button>
            <Link href="/recruiter/roles/new">
              <Button
                variant="primary"
                size="sm"
                leftIcon={<Plus className="h-3.5 w-3.5" strokeWidth={2} />}
              >
                New role
              </Button>
            </Link>
          </div>
        </div>

        {error && (
          <div className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
            {error}
          </div>
        )}

        {/* ── Needs action ───────────────────────────────────────────── */}
        {needsAction.length > 0 && (
          <section>
            <h2 className="text-h3 text-ink-900 mb-3">Needs your response</h2>
            <div className="space-y-2">{needsAction.map(renderIntroItem)}</div>
          </section>
        )}

        {/* ── Roles ────────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-h3 text-ink-900">Your roles</h2>
            {(data?.roles?.length ?? 0) > 0 && (
              <span className="text-micro text-ink-500">
                {data!.roles.length} role{data!.roles.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {loading && (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 rounded-lg bg-ink-100 animate-skeleton" />
              ))}
            </div>
          )}

          {!loading && (data?.roles ?? []).length === 0 && (
            <EmptyState
              icon={<Briefcase strokeWidth={1.5} />}
              title="No roles yet"
              description="Create your first role and Nitya will help you define the hiring brief."
              action={
                <Link href="/recruiter/roles/new">
                  <Button variant="primary" size="sm"
                    leftIcon={<Plus className="h-3.5 w-3.5" strokeWidth={2} />}>
                    Create role
                  </Button>
                </Link>
              }
            />
          )}

          {!loading && (data?.roles ?? []).length > 0 && (
            <div className="space-y-2">
              {data!.roles.map((r) => {
                const badgeMeta = ROLE_STATUS_BADGE[r.status] ?? { tone: "muted" as const };
                return (
                  <div
                    key={r.id}
                    className="rounded-lg border border-ink-100 bg-paper-1 px-4 py-3.5 hover:border-ink-300 hover:shadow-1 transition-all group"
                  >
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/recruiter/roles/${r.id}/intake`}
                        className="w-8 h-8 rounded-md bg-ink-900 flex items-center justify-center shrink-0"
                      >
                        <Briefcase className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
                      </Link>
                      <Link
                        href={`/recruiter/roles/${r.id}/intake`}
                        className="flex-1 min-w-0"
                      >
                        <div className="flex items-center gap-2">
                          <p className="text-body font-medium text-ink-900 truncate">
                            {r.title}
                          </p>
                          <Badge tone={badgeMeta.tone} className="capitalize shrink-0">
                            {r.status}
                          </Badge>
                        </div>
                        <p className="text-micro text-ink-500">
                          {r.pipeline_count} in pipeline
                        </p>
                      </Link>
                      <Link
                        href={`/recruiter/roles/${r.id}/pipeline`}
                        className="text-micro text-ink-500 hover:text-ink-800 shrink-0"
                      >
                        Pipeline
                      </Link>
                      <Link href={`/recruiter/roles/${r.id}/intake`}>
                        <ChevronRight
                          className="h-4 w-4 text-ink-300 group-hover:text-ink-500 transition-colors shrink-0"
                          strokeWidth={1.5}
                        />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* ── In progress ─────────────────────────────────────────── */}
        {inProgress.length > 0 && (
          <section>
            <h2 className="text-h3 text-ink-900 mb-3">In progress</h2>
            <div className="space-y-2">{inProgress.map(renderIntroItem)}</div>
          </section>
        )}

        {/* ── Other activity ───────────────────────────────────────── */}
        <section>
          <h2 className="text-h3 text-ink-900 mb-3">All intro activity</h2>

          {!loading && other.length === 0 && needsAction.length === 0 && inProgress.length === 0 && (
            <Card>
              <CardBody>
                <div className="flex items-center gap-3 text-ink-500 text-small py-2">
                  <Inbox className="h-5 w-5 text-ink-300" strokeWidth={1.5} />
                  <p>No intro activity yet. Nitya will notify you when candidates request intros.</p>
                </div>
              </CardBody>
            </Card>
          )}

          {!loading && other.length > 0 && (
            <div className="space-y-2">{other.map(renderIntroItem)}</div>
          )}
        </section>

    </div>
  );
}
