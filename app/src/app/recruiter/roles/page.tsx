"use client";

/**
 * Recruiter roles — list and manage hiring roles (pause / resume / close).
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Briefcase,
  ChevronRight,
  Kanban,
  Pause,
  Play,
  Plus,
  RefreshCw,
  XCircle,
} from "@/components/brand/icons";
import {
  formatCompRange,
  listRoles,
  updateRole,
  type RoleListItem,
} from "@/lib/api/recruiter";
import { getCachedProfile } from "@/lib/api/profile";
import { marketByCode, type MarketCode } from "@/lib/markets";
import { Badge, Button, Card, CardBody, EmptyState, useToast } from "@/components/ui";

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  active: "Hiring",
  hiring: "Hiring",
  paused: "Paused",
  closed: "Closed",
};

const STATUS_TONE: Record<string, "muted" | "strong" | "accent"> = {
  draft: "muted",
  active: "accent",
  hiring: "accent",
  paused: "muted",
  closed: "muted",
};

export default function RecruiterRolesPage() {
  const { toast } = useToast();
  const [market, setMarket] = useState<MarketCode>("IN");
  const [roles, setRoles] = useState<RoleListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRoles(await listRoles());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const m = getCachedProfile()?.user?.market;
    if (m) setMarket(marketByCode(m).code);
    void load();

    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  async function setStatus(roleId: string, status: string) {
    setUpdatingId(roleId);
    try {
      const updated = await updateRole(roleId, { status });
      setRoles((prev) =>
        prev.map((r) => (r.id === roleId ? { ...r, status: updated.status } : r))
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div className="px-4 md:px-6 py-6 space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-h2 font-semibold text-ink-900">Roles</h1>
          <p className="text-small text-ink-500 mt-0.5">
            Manage open roles, pause hiring, or close filled positions
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

      {loading && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 rounded-lg bg-ink-100 animate-skeleton" />
          ))}
        </div>
      )}

      {!loading && roles.length === 0 && (
        <EmptyState
          icon={<Briefcase strokeWidth={1.5} />}
          title="No roles yet"
          description="Create a role and Nitya will help you define the brief and find candidates."
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

      {!loading && roles.length > 0 && (
        <div className="space-y-2">
          {roles.map((role) => {
            const tone = STATUS_TONE[role.status] ?? "muted";
            const label = STATUS_LABEL[role.status] ?? role.status;
            const isClosed = role.status === "closed";
            const isPaused = role.status === "paused";
            const busy = updatingId === role.id;

            return (
              <Card key={role.id}>
                <CardBody className="space-y-3">
                  <div className="flex items-start gap-3">
                    <Link
                      href={`/recruiter/roles/${role.id}/intake`}
                      className="w-9 h-9 rounded-md bg-ink-900 flex items-center justify-center shrink-0"
                    >
                      <Briefcase className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
                    </Link>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={`/recruiter/roles/${role.id}/intake`}
                          className="text-small font-semibold text-ink-900 hover:underline truncate"
                        >
                          {role.title}
                        </Link>
                        <Badge tone={tone}>{label}</Badge>
                      </div>
                      <p className="text-micro text-ink-500 mt-0.5">
                        {[
                          role.location_city,
                          formatCompRange(role.comp_min, role.comp_max, { market }),
                        ]
                          .filter((x) => x && x !== "Not set")
                          .join(" · ") || "Details in intake"}
                      </p>
                    </div>
                    <Link
                      href={`/recruiter/roles/${role.id}/pipeline`}
                      className="text-ink-400 hover:text-ink-900 shrink-0"
                      title="Pipeline"
                    >
                      <Kanban className="h-4 w-4" strokeWidth={1.5} />
                    </Link>
                    <Link
                      href={`/recruiter/roles/${role.id}/intake`}
                      className="text-ink-400 hover:text-ink-900 shrink-0"
                    >
                      <ChevronRight className="h-4 w-4" strokeWidth={1.5} />
                    </Link>
                  </div>

                  <div className="flex flex-wrap gap-2 justify-end">
                    {!isClosed && !isPaused && (
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={busy}
                        leftIcon={<Pause className="h-3.5 w-3.5" strokeWidth={1.5} />}
                        onClick={() => void setStatus(role.id, "paused")}
                      >
                        Pause
                      </Button>
                    )}
                    {isPaused && (
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={busy}
                        leftIcon={<Play className="h-3.5 w-3.5" strokeWidth={1.5} />}
                        onClick={() => void setStatus(role.id, "active")}
                      >
                        Resume
                      </Button>
                    )}
                    {!isClosed && (
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={busy}
                        leftIcon={<XCircle className="h-3.5 w-3.5" strokeWidth={1.5} />}
                        onClick={() => void setStatus(role.id, "closed")}
                      >
                        Close
                      </Button>
                    )}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
