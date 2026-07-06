"use client";

/**
 * Recruiter dashboard — visual home with Nitya chats, stats, and candidate search.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Briefcase,
  ChevronRight,
  Inbox,
  MessageSquare,
  Plus,
  Search,
  User,
  Users,
} from "@/components/brand/icons";
import { NityaFace } from "@/components/nitya/NityaFace";
import {
  createRole,
  fetchRecruiterDashboard,
  fetchRecruiterProfile,
  listRoles,
  searchRecruiterCandidates,
  type RecruiterCandidateSearchHit,
  type RecruiterDashboardData,
  type RoleListItem,
} from "@/lib/api/recruiter";
import { Badge, Button, Card, CardBody, EmptyState, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

const ROLE_STATUS_TONE: Record<string, "muted" | "strong" | "accent"> = {
  draft: "muted",
  active: "accent",
  hiring: "accent",
  paused: "muted",
  closed: "muted",
};

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function StatCard({
  label,
  value,
  href,
  Icon,
}: {
  label: string;
  value: number;
  href: string;
  Icon: React.ElementType;
}) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-ink-100 bg-paper-1 px-4 py-3 hover:border-ink-200 hover:bg-ink-50 transition-colors"
    >
      <div className="flex items-center gap-2 text-micro text-ink-500">
        <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
        {label}
      </div>
      <p className="text-h2 font-semibold text-ink-900 mt-1">{value}</p>
    </Link>
  );
}

function CandidateHitCard({ hit }: { hit: RecruiterCandidateSearchHit }) {
  const subtitle = [hit.current_title, hit.current_company, hit.location_city]
    .filter(Boolean)
    .join(" · ");

  const href = hit.role_id
    ? `/recruiter/roles/${hit.role_id}/pipeline`
    : "/recruiter/roles";

  return (
    <Link
      href={href}
      className="flex items-center gap-3 rounded-lg border border-ink-100 bg-paper-1 px-4 py-3 hover:border-ink-200 transition-colors"
    >
      <div className="h-9 w-9 shrink-0 rounded-md bg-ink-900 flex items-center justify-center">
        <User className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-small font-medium text-ink-900 truncate">{hit.display_name}</p>
        <p className="text-micro text-ink-500 truncate">
          {subtitle || hit.headline || "Profile on Hireschema"}
        </p>
      </div>
      {hit.role_title ? (
        <Badge tone="muted" className="shrink-0 max-w-[140px] truncate">
          {hit.role_title}
        </Badge>
      ) : (
        <Badge tone="accent" className="shrink-0">
          Discover
        </Badge>
      )}
      <ChevronRight className="h-4 w-4 text-ink-300 shrink-0" strokeWidth={1.5} />
    </Link>
  );
}

/** Inline first-role creator — shown when a recruiter has no roles yet. */
function FirstRoleHero() {
  const router = useRouter();
  const { toast } = useToast();
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);

  async function create() {
    const t = title.trim();
    if (!t) return;
    setCreating(true);
    try {
      const created = await createRole({ title: t.slice(0, 120) });
      router.push(`/recruiter/roles/${created.role_id}/intake`);
    } catch (err) {
      toast.error((err as Error).message);
      setCreating(false);
    }
  }

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start gap-3">
          <NityaFace size="sm" />
          <div className="min-w-0">
            <p className="text-small font-semibold text-ink-900">
              What role should I start on?
            </p>
            <p className="text-micro text-ink-500 mt-0.5">
              Type a title and I&apos;ll open the intake chat — JD, budget, and
              must-haves happen there.
            </p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void create();
            }}
            placeholder="e.g. Senior Backend Engineer"
            className={cn(
              "flex-1 rounded-md border border-ink-100 bg-paper-1 px-3 py-2.5",
              "text-small text-ink-900 placeholder:text-ink-400",
              "focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring",
            )}
          />
          <Button
            variant="primary"
            size="md"
            loading={creating}
            disabled={!title.trim() || creating}
            onClick={() => void create()}
          >
            Start hiring
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

export default function RecruiterDashboardPage() {
  const { toast } = useToast();
  const [data, setData] = useState<RecruiterDashboardData | null>(null);
  const [roles, setRoles] = useState<RoleListItem[]>([]);
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchRoleId, setSearchRoleId] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<RecruiterCandidateSearchHit[]>([]);
  const [searchRan, setSearchRan] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashboard, roleList, profile] = await Promise.all([
        fetchRecruiterDashboard(),
        listRoles(),
        fetchRecruiterProfile(),
      ]);
      setData(dashboard);
      setRoles(roleList);
      setCompanyName(profile.company_name || null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();

    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  async function runSearch(e?: React.FormEvent) {
    e?.preventDefault();
    const q = searchQuery.trim();
    if (q.length < 2) {
      toast.error("Type at least 2 characters to search");
      return;
    }
    setSearching(true);
    setSearchRan(true);
    try {
      const res = await searchRecruiterCandidates(q, searchRoleId || undefined);
      setSearchResults(res.candidates);
    } catch (err) {
      toast.error((err as Error).message);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  const stats = data?.stats;

  return (
    <div className="px-4 md:px-6 py-6 space-y-8 max-w-4xl mx-auto">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-micro font-medium uppercase tracking-wide text-ink-400">
            Recruiter workspace
          </p>
          <h1 className="text-h2 font-semibold text-ink-900 mt-0.5">
            {companyName ?? "Dashboard"}
          </h1>
          <p className="text-small text-ink-500 mt-1">
            Your roles, Nitya chats, and candidate search in one place.
          </p>
        </div>
        <Link href="/recruiter/roles/new" className="shrink-0">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" strokeWidth={2} />}
          >
            New role
          </Button>
        </Link>
      </div>

      {error && (
        <div className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
          {error}
        </div>
      )}

      {!loading && roles.length === 0 && !error && <FirstRoleHero />}

      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard
          label="Active roles"
          value={stats?.active_roles ?? 0}
          href="/recruiter/roles"
          Icon={Briefcase}
        />
        <StatCard
          label="In pipeline"
          value={stats?.pipeline_total ?? 0}
          href="/recruiter/roles"
          Icon={Users}
        />
        <StatCard
          label="Pending intros"
          value={stats?.pending_intros ?? 0}
          href="/recruiter/inbox"
          Icon={Inbox}
        />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-h3 font-semibold text-ink-900">Find candidates</h2>
        </div>
        <Card>
          <CardBody className="space-y-3">
            <form onSubmit={(e) => void runSearch(e)} className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-400"
                  strokeWidth={1.5}
                />
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by name, title, company, or skill…"
                  className={cn(
                    "w-full rounded-md border border-ink-100 bg-paper-1 pl-9 pr-3 py-2.5",
                    "text-small text-ink-900 placeholder:text-ink-400",
                    "focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring",
                  )}
                />
              </div>
              <select
                value={searchRoleId}
                onChange={(e) => setSearchRoleId(e.target.value)}
                className="rounded-md border border-ink-100 bg-paper-1 px-3 py-2.5 text-small text-ink-900 focus:outline-none focus:border-accent"
                aria-label="Filter by role"
              >
                <option value="">All roles</option>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                  </option>
                ))}
              </select>
              <Button type="submit" variant="primary" size="md" loading={searching}>
                Search
              </Button>
            </form>
            {searchRan && (
              <div className="space-y-2 pt-1">
                {searchResults.length === 0 && !searching && (
                  <p className="text-small text-ink-500 py-2">
                    No candidates matched. Try a different keyword or run search from a role chat
                    with Nitya.
                  </p>
                )}
                {searchResults.map((hit) => (
                  <CandidateHitCard key={`${hit.candidate_id}-${hit.role_id ?? "d"}`} hit={hit} />
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-h3 font-semibold text-ink-900">Nitya chats</h2>
          <span className="text-micro text-ink-500">One thread per role</span>
        </div>

        {loading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-lg bg-ink-100 animate-skeleton" />
            ))}
          </div>
        )}

        {!loading && (data?.chats?.length ?? 0) === 0 && (
          <EmptyState
            icon={<MessageSquare strokeWidth={1.5} />}
            title="No chats yet"
            description="Create a role and Nitya will open an intake chat tagged to that job."
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

        {!loading && (data?.chats?.length ?? 0) > 0 && (
          <div className="space-y-2">
            {data!.chats.map((chat) => {
              const roleId = chat.role_id;
              const href = roleId ? `/recruiter/roles/${roleId}/intake` : "/recruiter/roles";
              const tone = ROLE_STATUS_TONE[chat.role_status ?? ""] ?? "muted";
              return (
                <Link
                  key={chat.id}
                  href={href}
                  className="flex items-center gap-3 rounded-lg border border-ink-100 bg-paper-1 px-4 py-3.5 hover:border-ink-200 hover:shadow-1 transition-all group"
                >
                  <div className="h-9 w-9 shrink-0 rounded-md bg-ink-900 flex items-center justify-center">
                    <MessageSquare className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      {chat.role_title && (
                        <Badge tone={tone} className="shrink-0 max-w-[200px] truncate">
                          {chat.role_title}
                        </Badge>
                      )}
                      <span className="text-micro text-ink-400">{timeAgo(chat.updated_at)}</span>
                    </div>
                    <p className="text-small text-ink-800 mt-0.5 truncate">
                      {chat.last_message || chat.title || "Open chat with Nitya"}
                    </p>
                  </div>
                  <ChevronRight
                    className="h-4 w-4 text-ink-300 group-hover:text-ink-500 transition-colors shrink-0"
                    strokeWidth={1.5}
                  />
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {(data?.roles?.length ?? 0) > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-h3 font-semibold text-ink-900">Your roles</h2>
            <Link href="/recruiter/roles" className="text-micro text-ink-500 hover:text-ink-900">
              View all
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {data!.roles.map((role) => (
              <Link
                key={role.id}
                href={`/recruiter/roles/${role.id}/intake`}
                className="rounded-lg border border-ink-100 bg-paper-1 px-4 py-3 hover:border-ink-200 transition-colors"
              >
                <p className="text-small font-medium text-ink-900 truncate">{role.title}</p>
                <p className="text-micro text-ink-500 mt-0.5">
                  {role.pipeline_count} in pipeline
                  {role.location_city ? ` · ${role.location_city}` : ""}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
