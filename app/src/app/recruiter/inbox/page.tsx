"use client";

/**
 * Recruiter inbox — roles strip + master/detail intro chats.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Briefcase,
  ChevronRight,
  Plus,
  RefreshCw,
} from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import {
  RecruiterIntrosInboxPanel,
  useRecruiterInboxRealtime,
  type RecruiterInboxItem,
} from "@/components/intros/RecruiterIntrosInboxPanel";
import { Badge, Button, EmptyState } from "@/components/ui";
import { RecruiterBreadcrumbs } from "@/components/ux";
import { ShareRoleLink } from "@/components/recruiter/ShareRoleLink";

type RoleRow = {
  id: string;
  title: string;
  status: string;
  pipeline_count: number;
  public_role_url?: string | null;
};

type InboxData = {
  items: RecruiterInboxItem[];
  roles: RoleRow[];
};

const ROLE_STATUS_BADGE: Record<string, { tone: "muted" | "strong" | "accent" }> = {
  active: { tone: "accent" },
  paused: { tone: "muted" },
  closed: { tone: "muted" },
  draft: { tone: "muted" },
};

export default function RecruiterInboxPage() {
  const searchParams = useSearchParams();
  const selectedIntroId = searchParams.get("intro_id");
  const [data, setData] = useState<InboxData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
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
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useRecruiterInboxRealtime(() => {
    void load();
  });

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 px-4 md:px-6 py-4 border-b border-ink-100 space-y-4">
        <RecruiterBreadcrumbs crumbs={[{ label: "Inbox" }]} />

        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-h2 font-semibold text-ink-900">Inbox</h1>
            <p className="text-small text-ink-500 mt-0.5">
              Candidate intros and direct chats
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

        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-small font-semibold text-ink-900">Your roles</h2>
            {(data?.roles?.length ?? 0) > 0 && (
              <span className="text-micro text-ink-500">
                {data!.roles.length} role{data!.roles.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {loading && !data && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {[1, 2].map((i) => (
                <div key={i} className="h-16 w-48 shrink-0 rounded-lg bg-ink-100 animate-skeleton" />
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

          {(data?.roles ?? []).length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {data!.roles.map((r) => {
                const badgeMeta = ROLE_STATUS_BADGE[r.status] ?? { tone: "muted" as const };
                return (
                  <div
                    key={r.id}
                    className="shrink-0 w-[min(100%,240px)] rounded-lg border border-ink-100 bg-paper-1 px-3 py-2.5 hover:border-ink-200 transition-colors"
                  >
                    <div className="flex items-start gap-2">
                      <Link
                        href={`/recruiter/roles/${r.id}/intake`}
                        className="min-w-0 flex-1"
                      >
                        <p className="text-small font-medium text-ink-900 truncate">
                          {r.title}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge tone={badgeMeta.tone} className="capitalize text-[10px]">
                            {r.status}
                          </Badge>
                          <span className="text-micro text-ink-500">
                            {r.pipeline_count} in pipeline
                          </span>
                        </div>
                      </Link>
                      <ShareRoleLink publicRoleUrl={r.public_role_url} />
                      <Link href={`/recruiter/roles/${r.id}/pipeline`}>
                        <ChevronRight className="h-4 w-4 text-ink-300" strokeWidth={1.5} />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <div className="flex-1 min-h-0">
        <RecruiterIntrosInboxPanel
          items={data?.items ?? []}
          loading={loading && !data}
          initialSelectedIntroId={selectedIntroId}
          onItemsChange={(items) =>
            setData((prev) => (prev ? { ...prev, items } : prev))
          }
        />
      </div>
    </div>
  );
}
