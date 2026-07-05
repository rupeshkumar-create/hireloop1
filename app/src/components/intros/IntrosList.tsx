"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Building2,
  CheckCircle,
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
import { IntroChat } from "@/components/intros/IntroChat";
import { IntroStatusTimeline, WarmHandoffCard } from "@/components/ux";
import { FadeUp } from "@/components/ui/motion";
import { Badge, Button, Card, CardBody, EmptyState, useToast } from "@/components/ui";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const STATUS_META: Record<
  string,
  { tone: "muted" | "strong" | "accent"; label: string; Icon: typeof Clock }
> = {
  pending: { tone: "muted", label: "Pending", Icon: Clock },
  invited: { tone: "accent", label: "Invite sent", Icon: Clock },
  recruiter_notified: { tone: "accent", label: "Notified", Icon: Clock },
  draft_ready: { tone: "accent", label: "Email drafted", Icon: Clock },
  sent: { tone: "strong", label: "Intro sent", Icon: CheckCircle },
  accepted: { tone: "strong", label: "Accepted", Icon: CheckCircle },
  declined: { tone: "muted", label: "Declined", Icon: XCircle },
  expired: { tone: "muted", label: "Expired", Icon: XCircle },
  cancelled: { tone: "muted", label: "Cancelled", Icon: XCircle },
};

type IntrosListProps = {
  /** panel = dashboard inbox; page = full /intros route */
  variant?: "panel" | "page";
  className?: string;
};

export function IntrosList({ variant = "page", className }: IntrosListProps) {
  const { toast } = useToast();
  const cached = getCachedIntros();
  const [intros, setIntros] = useState<IntroRequest[]>(cached ?? []);
  const [loading, setLoading] = useState(cached === null);
  const [error, setError] = useState<string | null>(null);
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

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("intro_requests:candidate")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "intro_requests" },
        () => {
          void load();
        },
      )
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
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

  function timeAgo(iso: string) {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (d === 0) return "Today";
    if (d === 1) return "Yesterday";
    return variant === "panel" ? `${d}d ago` : `${d} days ago`;
  }

  if (loading) {
    return (
      <div className={cn("space-y-3", variant === "panel" ? "p-5" : "", className)}>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 rounded-lg bg-ink-100 animate-skeleton" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn(variant === "panel" ? "p-5" : "", className)}>
        <p className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
          {error}
        </p>
      </div>
    );
  }

  if (intros.length === 0) {
    return (
      <div className={cn(variant === "panel" ? "p-5" : "", className)}>
        <EmptyState
          icon={<Building2 strokeWidth={1.5} />}
          title="No intro requests yet"
          description="Ask Aarya to request an intro for any job match. She'll draft a warm email to the hiring manager via your Gmail."
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
      </div>
    );
  }

  return (
    <div
      className={cn(
        "space-y-3",
        variant === "panel" ? "p-5" : "",
        className,
      )}
    >
      {intros.map((intro) => {
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
        const showFull = variant === "page";

        const card = (
          <Card
            className={cn(
              "transition-opacity",
              ["cancelled", "expired"].includes(intro.status) && "opacity-60",
            )}
          >
            <CardBody>
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-md bg-ink-100 flex items-center justify-center shrink-0 mt-0.5">
                  <Building2 className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 mb-0.5">
                    <p className="text-small font-medium text-ink-900 truncate">
                      {intro.job_title}
                    </p>
                    <Badge tone={meta.tone} className="shrink-0 text-[10px]">
                      {showFull && <Icon className="h-3 w-3 mr-1" strokeWidth={2} />}
                      {meta.label}
                    </Badge>
                  </div>
                  {intro.company_name && (
                    <p className="text-micro text-ink-500 truncate">
                      {intro.company_name}
                      {intro.hm_name && ` · ${intro.hm_name}`}
                    </p>
                  )}
                  {showFull && (
                    <>
                      <IntroStatusTimeline status={intro.status} className="mt-2" />
                      <WarmHandoffCard
                        recruiterName={intro.hm_name}
                        companyName={intro.company_name}
                        jobTitle={intro.job_title}
                      />
                    </>
                  )}
                  {fromRecruiter && showFull && (
                    <p className="text-small text-accent mt-1.5 font-medium">
                      {intro.hm_name ?? "A recruiter"} wants to connect about this role
                    </p>
                  )}
                  {intro.replied_at && (
                    <p className="text-micro text-accent font-medium mt-1">
                      Replied {timeAgo(intro.replied_at)}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-1.5">
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
                    ) : canChat && showFull ? (
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
                  {canChat && showFull && chatOpen && (
                    <IntroChat introId={intro.id} side="candidate" />
                  )}
                </div>
              </div>
            </CardBody>
          </Card>
        );

        return showFull ? <FadeUp key={intro.id}>{card}</FadeUp> : <div key={intro.id}>{card}</div>;
      })}
    </div>
  );
}
