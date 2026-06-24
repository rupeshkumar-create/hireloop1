"use client";

/**
 * Super admin panel — internal user management.
 *
 * Guard: enforced server-side by /admin/layout.tsx (calls /api/v1/admin/dashboard).
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Search, ShieldAlert, Trash2 } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { Badge, Button, EmptyState, Input, Select } from "@/components/ui";
import { cn } from "@/lib/utils";

type UserSummary = {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  role: "candidate" | "recruiter" | "admin";
  india_verified: boolean;
  created_at: string;
  deleted_at: string | null;
  candidate_id: string | null;
  candidate_is_active: boolean | null;
  recruiter_id: string | null;
  recruiter_deleted_at: string | null;
};

type CandidateSummary = {
  id: string;
  user_id: string;
  headline: string | null;
  current_title: string | null;
  location_city: string | null;
  years_experience: number | null;
  is_active: boolean;
  deleted_at: string | null;
  user_email: string;
  user_name: string | null;
};

type RecruiterSummary = {
  id: string;
  user_id: string;
  title: string | null;
  company_id: string | null;
  deleted_at: string | null;
  user_email: string;
  user_name: string | null;
};

type Tab = "users" | "candidates" | "recruiters";

const ROLE_OPTIONS = [
  { value: "candidate", label: "candidate" },
  { value: "recruiter", label: "recruiter" },
  { value: "admin", label: "admin" },
] as const;

export default function SuperAdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  const [q, setQ] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [users, setUsers] = useState<UserSummary[]>([]);
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [recruiters, setRecruiters] = useState<RecruiterSummary[]>([]);

  const endpoint = useMemo(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (includeDeleted) params.set("include_deleted", "true");
    params.set("limit", "100");
    params.set("offset", "0");

    if (tab === "users") return `/api/v1/super-admin/users?${params.toString()}`;
    if (tab === "candidates") return `/api/v1/super-admin/candidates?${params.toString()}`;
    return `/api/v1/super-admin/recruiters?${params.toString()}`;
  }, [tab, q, includeDeleted]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      if (tab === "users") {
        const data = await apiFetch<UserSummary[]>(endpoint);
        setUsers(data);
      } else if (tab === "candidates") {
        const data = await apiFetch<CandidateSummary[]>(endpoint);
        setCandidates(data);
      } else {
        const data = await apiFetch<RecruiterSummary[]>(endpoint);
        setRecruiters(data);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint]);

  async function updateUser(userId: string, patch: Partial<{ role: UserSummary["role"]; india_verified: boolean }>) {
    await apiFetch<UserSummary>(`/api/v1/super-admin/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    await load();
  }

  async function deleteUser(userId: string) {
    const ok = window.confirm("Soft-delete this user? (DPDP purge scheduled in 30 days)");
    if (!ok) return;
    await apiFetch<{ ok: true }>(`/api/v1/super-admin/users/${userId}`, { method: "DELETE" });
    await load();
  }

  async function setCandidateActive(candidateId: string, isActive: boolean) {
    await apiFetch<CandidateSummary>(`/api/v1/super-admin/candidates/${candidateId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
    await load();
  }

  async function setRecruiterEnabled(recruiterId: string, enabled: boolean) {
    await apiFetch<RecruiterSummary>(`/api/v1/super-admin/recruiters/${recruiterId}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
    await load();
  }

  return (
    <main className="min-h-screen bg-ink-900 text-paper-0 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <Link href="/admin" className="text-ink-500 hover:text-paper-0 transition-colors mt-1">
              <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
            </Link>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <ShieldAlert className="h-5 w-5 text-accent" strokeWidth={1.5} />
                <span className="text-micro text-ink-500 uppercase tracking-wider">
                  Super admin
                </span>
              </div>
              <h1 className="text-h1 text-paper-0">User management</h1>
              <p className="text-small text-ink-500">
                Soft-delete users, toggle candidates, enable/disable recruiters.
              </p>
            </div>
          </div>

          <Button variant="secondary" size="sm" onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>

        {/* Controls */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex items-center gap-2">
            <TabButton active={tab === "users"} onClick={() => setTab("users")}>
              Users
            </TabButton>
            <TabButton active={tab === "candidates"} onClick={() => setTab("candidates")}>
              Candidates
            </TabButton>
            <TabButton active={tab === "recruiters"} onClick={() => setTab("recruiters")}>
              Recruiters
            </TabButton>
          </div>

          <div className="flex-1 sm:max-w-md">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by email or name…"
            />
          </div>

          <label className="flex items-center gap-2 text-small text-ink-300 select-none">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => setIncludeDeleted(e.target.checked)}
            />
            Include deleted
          </label>
        </div>

        {error && (
          <div className="rounded-md bg-destructive-bg border border-destructive px-4 py-3 text-destructive text-small">
            {error}
          </div>
        )}

        {/* Content */}
        {tab === "users" && (
          <UsersTable
            rows={users}
            loading={loading}
            onDelete={deleteUser}
            onUpdate={updateUser}
          />
        )}

        {tab === "candidates" && (
          <CandidatesTable
            rows={candidates}
            loading={loading}
            onToggleActive={setCandidateActive}
          />
        )}

        {tab === "recruiters" && (
          <RecruitersTable
            rows={recruiters}
            loading={loading}
            onToggleEnabled={setRecruiterEnabled}
          />
        )}
      </div>
    </main>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-3.5 h-9 rounded-full text-small font-medium transition-colors",
        active
          ? "bg-paper-1 text-ink-900"
          : "bg-ink-900 border border-ink-700 text-paper-0 hover:bg-ink-700/40"
      )}
    >
      {children}
    </button>
  );
}

function UsersTable({
  rows,
  loading,
  onDelete,
  onUpdate,
}: {
  rows: UserSummary[];
  loading: boolean;
  onDelete: (userId: string) => Promise<void>;
  onUpdate: (userId: string, patch: Partial<{ role: UserSummary["role"]; india_verified: boolean }>) => Promise<void>;
}) {
  if (!loading && rows.length === 0) {
    return (
      <EmptyState
        icon={<Search strokeWidth={1.5} />}
        title="No users"
        description="Try a different search."
      />
    );
  }

  return (
    <div className="rounded-lg border border-ink-700 overflow-hidden">
      <table className="w-full text-small">
        <thead className="bg-ink-700">
          <tr>
            {["Email", "Name", "Role", "OTP", "Candidate", "Recruiter", "Created", ""].map((h) => (
              <th
                key={h}
                className="text-left px-4 py-3 text-micro text-ink-300 uppercase tracking-wider font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700">
          {rows.map((u) => (
            <tr key={u.id} className="hover:bg-ink-700/30 transition-colors">
              <td className="px-4 py-3 font-medium text-paper-0">{u.email}</td>
              <td className="px-4 py-3 text-ink-300">{u.full_name ?? "—"}</td>
              <td className="px-4 py-3">
                <Select
                  value={u.role}
                  options={ROLE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                  className="bg-ink-900 border-ink-700 text-paper-0 h-9 py-0 rounded-md px-3"
                  onChange={(e) => void onUpdate(u.id, { role: e.target.value as UserSummary["role"] })}
                />
              </td>
              <td className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => void onUpdate(u.id, { india_verified: !u.india_verified })}
                  className={cn(
                    "px-2.5 py-1 rounded-full text-micro font-semibold border transition-colors",
                    u.india_verified
                      ? "bg-ink-900 border-ink-700 text-paper-0 hover:bg-ink-700/40"
                      : "bg-destructive/10 border-destructive/30 text-destructive hover:bg-destructive/15"
                  )}
                >
                  {u.india_verified ? "Verified" : "Not verified"}
                </button>
              </td>
              <td className="px-4 py-3">
                {u.candidate_id ? (
                  <Badge tone={u.candidate_is_active ? "accent" : "muted"}>
                    {u.candidate_is_active ? "Active" : "Paused"}
                  </Badge>
                ) : (
                  <span className="text-ink-500">—</span>
                )}
              </td>
              <td className="px-4 py-3">
                {u.recruiter_id ? (
                  <Badge tone={u.recruiter_deleted_at ? "muted" : "accent"}>
                    {u.recruiter_deleted_at ? "Disabled" : "Enabled"}
                  </Badge>
                ) : (
                  <span className="text-ink-500">—</span>
                )}
              </td>
              <td className="px-4 py-3 text-ink-500 text-micro">
                {new Date(u.created_at).toLocaleDateString("en-IN")}
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={() => void onDelete(u.id)}
                  className="inline-flex items-center gap-1.5 text-destructive hover:text-red-300 transition-colors"
                  title="Soft delete"
                >
                  <Trash2 className="h-4 w-4" strokeWidth={1.5} />
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CandidatesTable({
  rows,
  loading,
  onToggleActive,
}: {
  rows: CandidateSummary[];
  loading: boolean;
  onToggleActive: (candidateId: string, active: boolean) => Promise<void>;
}) {
  if (!loading && rows.length === 0) {
    return (
      <EmptyState
        icon={<Search strokeWidth={1.5} />}
        title="No candidates"
        description="Try a different search."
      />
    );
  }

  return (
    <div className="rounded-lg border border-ink-700 overflow-hidden">
      <table className="w-full text-small">
        <thead className="bg-ink-700">
          <tr>
            {["Email", "Name", "Title", "City", "Exp", "Status", ""].map((h) => (
              <th
                key={h}
                className="text-left px-4 py-3 text-micro text-ink-300 uppercase tracking-wider font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700">
          {rows.map((c) => (
            <tr key={c.id} className="hover:bg-ink-700/30 transition-colors">
              <td className="px-4 py-3 font-medium text-paper-0">{c.user_email}</td>
              <td className="px-4 py-3 text-ink-300">{c.user_name ?? "—"}</td>
              <td className="px-4 py-3 text-ink-300">{c.current_title ?? c.headline ?? "—"}</td>
              <td className="px-4 py-3 text-ink-300">{c.location_city ?? "—"}</td>
              <td className="px-4 py-3 text-ink-300">
                {c.years_experience != null ? `${c.years_experience}y` : "—"}
              </td>
              <td className="px-4 py-3">
                <Badge tone={c.is_active ? "accent" : "muted"}>
                  {c.is_active ? "Active" : "Paused"}
                </Badge>
              </td>
              <td className="px-4 py-3 text-right">
                <Button
                  variant={c.is_active ? "secondary" : "primary"}
                  size="sm"
                  onClick={() => void onToggleActive(c.id, !c.is_active)}
                >
                  {c.is_active ? "Pause" : "Activate"}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecruitersTable({
  rows,
  loading,
  onToggleEnabled,
}: {
  rows: RecruiterSummary[];
  loading: boolean;
  onToggleEnabled: (recruiterId: string, enabled: boolean) => Promise<void>;
}) {
  if (!loading && rows.length === 0) {
    return (
      <EmptyState
        icon={<Search strokeWidth={1.5} />}
        title="No recruiters"
        description="Try a different search."
      />
    );
  }

  return (
    <div className="rounded-lg border border-ink-700 overflow-hidden">
      <table className="w-full text-small">
        <thead className="bg-ink-700">
          <tr>
            {["Email", "Name", "Title", "Company", "Status", ""].map((h) => (
              <th
                key={h}
                className="text-left px-4 py-3 text-micro text-ink-300 uppercase tracking-wider font-semibold"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700">
          {rows.map((r) => {
            const enabled = !r.deleted_at;
            return (
              <tr key={r.id} className="hover:bg-ink-700/30 transition-colors">
                <td className="px-4 py-3 font-medium text-paper-0">{r.user_email}</td>
                <td className="px-4 py-3 text-ink-300">{r.user_name ?? "—"}</td>
                <td className="px-4 py-3 text-ink-300">{r.title ?? "—"}</td>
                <td className="px-4 py-3 text-ink-300">
                  {r.company_id ? r.company_id.slice(0, 8) + "…" : "—"}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={enabled ? "accent" : "muted"}>
                    {enabled ? "Enabled" : "Disabled"}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-right">
                  <Button
                    variant={enabled ? "secondary" : "primary"}
                    size="sm"
                    onClick={() => void onToggleEnabled(r.id, !enabled)}
                  >
                    {enabled ? "Disable" : "Enable"}
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
