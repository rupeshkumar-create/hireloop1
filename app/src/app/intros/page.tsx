"use client";

/**
 * Intros page — P14 candidate view
 * Lists all intro requests and their current status.
 * Candidates can cancel pending intros.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Building2,
  CheckCircle,
  Clock,
  MessageCircle,
  XCircle,
} from "lucide-react";
import {
  cancelIntro,
  fetchIntros,
  getCachedIntros,
  respondToIntro,
  type IntroRequest,
} from "@/lib/api/intros";
import { AppShell } from "@/components/layout/AppShell";
import { IntroChat } from "@/components/intros/IntroChat";
import { BackToAaryaLink, IntroStatusTimeline, ScoringExplainerLink, WarmHandoffCard } from "@/components/ux";
import { FadeUp } from "@/components/ui/motion";
import { Badge, Button, Card, CardBody, EmptyState, useToast } from "@/components/ui";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const STATUS_META: Record<
  string,
  { tone: "muted" | "strong" | "accent"; label: string; Icon: typeof Clock }
> = {
  pending:            { tone: "muted",   label: "Pending",          Icon: Clock        },
  invited:            { tone: "accent",  label: "Invite sent",      Icon: Clock        },
  recruiter_notified: { tone: "accent",  label: "Notified",         Icon: Clock        },
  draft_ready:        { tone: "accent",  label: "Email drafted",    Icon: Clock        },
  sent:               { tone: "strong",  label: "Intro sent ✓",     Icon: CheckCircle  },
  accepted:           { tone: "strong",  label: "Accepted ✓",       Icon: CheckCircle  },
  declined:           { tone: "muted",   label: "Declined",         Icon: XCircle      },
  expired:            { tone: "muted",   label: "Expired",          Icon: XCircle      },
  cancelled:          { tone: "muted",   label: "Cancelled",        Icon: XCircle      },
};

export default function IntrosPage() {
  const { toast } = useToast();
  const cached = getCachedIntros();
  const [intros, setIntros]   = useState<IntroRequest[]>(cached ?? []);
  const [loading, setLoading] = useState(cached === null);
  const [error, setError]     = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [responding, setResponding] = useState<string | null>(null);
  const [openChat, setOpenChat] = useState<Set<string>>(new Set());

  async function load() {
    setError(null);
    try {
      const data = await fetchIntros({ force: true });
      setIntros(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  // Live status: refetch when any of the candidate's intros change (RLS scopes
  // delivery to their own rows). Covers recruiter-initiated intros + accepts.
  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("intro_requests:candidate")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "intro_requests" },
        () => { void load(); }
      )
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, []);

  async function cancel(introId: string) {
    setCancelling(introId);
    try {
      await cancelIntro(introId);
      setIntros((prev) =>
        prev.map((i) =>
          i.id === introId ? { ...i, status: "cancelled" } : i
        )
      );
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
            : i
        )
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setResponding(null);
    }
  }

  function timeAgo(iso: string) {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (d === 0) return "Today";
    if (d === 1) return "Yesterday";
    return `${d} days ago`;
  }

  return (
    <AppShell
      title="Intro requests"
      activeNav="intros"
      backContext="Continue in chat"
      action={
        <Link href="/dashboard">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />}
          >
            Ask for intro
          </Button>
        </Link>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <BackToAaryaLink />
          <ScoringExplainerLink />
        </div>

        {error && (
          <div className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
            {error}
          </div>
        )}

        {/* Skeleton */}
        {loading && Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg bg-ink-100 animate-skeleton" />
        ))}

        {/* Empty */}
        {!loading && !error && intros.length === 0 && (
          <EmptyState
            icon={<Building2 strokeWidth={1.5} />}
            title="No intro requests yet"
            description="Ask Aarya to request an intro for any job match. She'll draft a warm cold email to the hiring manager via your Gmail."
            action={
              <Link href="/dashboard">
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />}
                >
                  Ask Aarya
                </Button>
              </Link>
            }
          />
        )}

        {/* List */}
        {!loading && intros.map((intro) => {
          const meta = STATUS_META[intro.status] ?? {
            tone: "muted" as const,
            label: intro.status,
            Icon: Clock,
          };
          const { Icon } = meta;
          const fromRecruiter = intro.direction === "recruiter_to_candidate";
          const canRespond = fromRecruiter && intro.status === "pending";
          const canCancel =
            !fromRecruiter &&
            ["pending", "invited", "recruiter_notified"].includes(intro.status);
          const canChat = intro.status === "accepted";
          const chatOpen = openChat.has(intro.id);

          return (
            <FadeUp key={intro.id}>
            <Card className={cn(
              "transition-opacity",
              intro.status === "cancelled" || intro.status === "expired"
                ? "opacity-60"
                : ""
            )}>
              <CardBody>
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-md bg-ink-100 flex items-center justify-center shrink-0 mt-0.5">
                    <Building2 className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-body font-medium text-ink-900 truncate">
                          {intro.job_title}
                        </p>
                        {intro.company_name && (
                          <p className="text-small text-ink-500 truncate">
                            {intro.company_name}
                            {intro.hm_name && (
                              <span> · {intro.hm_name}</span>
                            )}
                          </p>
                        )}
                      </div>
                      <Badge tone={meta.tone} className="shrink-0 normal-case">
                        <Icon className="h-3 w-3 mr-1" strokeWidth={2} />
                        {meta.label}
                      </Badge>
                    </div>

                    <IntroStatusTimeline status={intro.status} className="mt-2" />
                    <WarmHandoffCard
                      recruiterName={intro.hm_name}
                      companyName={intro.company_name}
                      jobTitle={intro.job_title}
                    />

                    {fromRecruiter && (
                      <p className="text-small text-accent mt-1.5 font-medium">
                        {intro.hm_name ?? "A recruiter"} wants to connect about this role
                      </p>
                    )}

                    {intro.replied_at && (
                      <p className="text-small text-accent mt-1.5 font-medium">
                        Replied {timeAgo(intro.replied_at)}
                      </p>
                    )}

                    <div className="flex items-center justify-between mt-2">
                      <span className="text-micro text-ink-300">
                        {timeAgo(intro.created_at)}
                      </span>
                      {canRespond ? (
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void respond(intro.id, false)}
                            disabled={responding === intro.id}
                          >
                            Decline
                          </Button>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => void respond(intro.id, true)}
                            loading={responding === intro.id}
                          >
                            Accept
                          </Button>
                        </div>
                      ) : canChat ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() =>
                            setOpenChat((prev) => {
                              const next = new Set(prev);
                              if (next.has(intro.id)) next.delete(intro.id);
                              else next.add(intro.id);
                              return next;
                            })
                          }
                        >
                          {chatOpen ? "Hide chat" : "Open chat"}
                        </Button>
                      ) : canCancel ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void cancel(intro.id)}
                          loading={cancelling === intro.id}
                        >
                          Cancel
                        </Button>
                      ) : null}
                    </div>

                    {canChat && chatOpen && (
                      <IntroChat introId={intro.id} side="candidate" />
                    )}
                  </div>
                </div>
              </CardBody>
            </Card>
            </FadeUp>
          );
        })}
      </div>
    </AppShell>
  );
}
