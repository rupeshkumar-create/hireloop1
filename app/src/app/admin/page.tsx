"use client";

/**
 * Admin home — P23 (launch blocker)
 * Internal panel: platform stats, bias audit sample, DPDP compliance links.
 *
 * Uses the design system ink-900 bg for "admin mode" distinction.
 * Accessible only to users with role = admin.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  BarChart3,
  Users,
  Briefcase,
  Activity,
  ShieldAlert,
  ExternalLink,
  RefreshCw,
} from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import { Badge, Button, Card, CardBody, CardHeader } from "@/components/ui";

type DashStats = {
  total_users: number;
  candidates: number;
  recruiters: number;
  active_jobs: number;
  intros_7d: number;
  intros_sent_7d: number;
  voice_sessions_7d: number;
  placements_total: number;
};

type BiasRow = Record<string, unknown>;

const STAT_META: {
  key: keyof DashStats;
  label: string;
  Icon: typeof Users;
  accent?: boolean;
}[] = [
  { key: "total_users",         label: "Users",        Icon: Users       },
  { key: "candidates",          label: "Candidates",   Icon: Users       },
  { key: "recruiters",          label: "Recruiters",   Icon: Briefcase   },
  { key: "active_jobs",         label: "Active jobs",  Icon: Briefcase   },
  { key: "intros_7d",           label: "Intros (7d)",  Icon: BarChart3   },
  { key: "intros_sent_7d",      label: "Sent (7d)",    Icon: Activity    },
  { key: "voice_sessions_7d",   label: "Voice (7d)",   Icon: Activity    },
  { key: "placements_total",    label: "Placements",   Icon: BarChart3, accent: true },
];

export default function AdminHomePage() {
  const [stats, setStats]   = useState<DashStats | null>(null);
  const [bias, setBias]     = useState<BiasRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [s, b] = await Promise.all([
        apiFetch<DashStats>("/api/v1/admin/dashboard"),
        apiFetch<BiasRow[]>("/api/v1/admin/bias-audit?limit=5"),
      ]);
      setStats(s);
      setBias(b);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <main className="min-h-screen bg-ink-900 text-paper-0 p-6">
      <div className="max-w-5xl mx-auto space-y-8">

        {/* ── Header ───────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <ShieldAlert className="h-5 w-5 text-accent" strokeWidth={1.5} />
              <span className="text-micro text-ink-500 uppercase tracking-wider">
                Admin panel
              </span>
            </div>
            <h1 className="text-h1 text-paper-0">Platform overview</h1>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void load()}
            loading={loading}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
          >
            Refresh
          </Button>
        </div>

        {error && (
          <div className="rounded-md bg-destructive-bg border border-destructive px-4 py-3 text-destructive text-small">
            {error}
          </div>
        )}

        {/* ── Stats grid ───────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {STAT_META.map(({ key, label, Icon, accent }) => (
            <div
              key={key}
              className="rounded-lg bg-ink-900 border border-ink-700 p-4 space-y-2"
            >
              <div className="flex items-center justify-between">
                <p className="text-micro text-ink-500 uppercase tracking-wider">
                  {label}
                </p>
                <Icon
                  className={`h-3.5 w-3.5 ${accent ? "text-accent" : "text-ink-500"}`}
                  strokeWidth={1.5}
                />
              </div>
              <p className={`text-h2 font-semibold ${accent ? "text-accent" : "text-paper-0"}`}>
                {loading ? "—" : (stats?.[key] ?? 0).toLocaleString("en-IN")}
              </p>
            </div>
          ))}
        </div>

        {/* ── Quick nav ────────────────────────────────────────────────────── */}
        <div className="flex flex-wrap gap-3">
          {[
            { href: "/admin/placements", label: "Placements", note: "manual billing" },
            { href: "/admin/super",     label: "Super admin", note: "users + recruiters" },
          ].map(({ href, label, note }) => (
            <Link
              key={href}
              href={href}
              className="
                flex items-center gap-2 rounded-md border border-ink-700
                px-4 py-2.5 text-small text-paper-0
                hover:border-ink-500 hover:bg-ink-700 transition-colors
              "
            >
              <ExternalLink className="h-3.5 w-3.5 text-ink-500" strokeWidth={1.5} />
              {label}
              <span className="text-ink-500">— {note}</span>
            </Link>
          ))}
        </div>

        {/* ── Bias audit sample ─────────────────────────────────────────────── */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-h3 text-paper-0">Bias audit sample (last 5)</h2>
            <Badge tone="muted">DPDP Act 2023</Badge>
          </div>

          {bias.length === 0 && !loading && (
            <p className="text-small text-ink-500">No bias audit records yet.</p>
          )}

          <div className="space-y-2">
            {bias.map((row, idx) => {
              const anyRow = row as Record<string, unknown>;
              const id =
                (typeof anyRow.match_score_id === "string" && anyRow.match_score_id) ||
                (typeof anyRow.id === "string" && anyRow.id) ||
                `row_${idx}`;
              const score =
                (typeof anyRow.overall_score === "number" && anyRow.overall_score) ||
                (typeof anyRow.llm_score === "number" && anyRow.llm_score) ||
                null;
              const createdAt =
                (typeof anyRow.created_at === "string" && anyRow.created_at) || null;

              return (
              <div
                key={id}
                className="rounded-md border border-ink-700 bg-ink-900 px-4 py-3 text-small"
              >
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-ink-500 font-mono text-micro">
                    {id.slice(0, 8)}…
                  </span>
                  {score != null && (
                    <Badge
                      tone={score >= 0.7 ? "accent" : score >= 0.5 ? "muted" : "strong"}
                    >
                      {Math.round(score * 100)}% match
                    </Badge>
                  )}
                  <span className="text-ink-500 ml-auto text-micro">
                    {createdAt ? new Date(createdAt).toLocaleDateString("en-IN") : "—"}
                  </span>
                </div>
                <pre className="text-micro text-ink-300 overflow-auto max-h-24 font-mono">
                  {JSON.stringify(anyRow.bias_audit ?? anyRow, null, 2)}
                </pre>
              </div>
              );
            })}
          </div>
        </section>

        {/* ── DPDP export queue note ───────────────────────────────────────── */}
        <Card className="border-ink-700 bg-ink-900">
          <CardHeader
            title="DPDP Act 2023 compliance"
            description="Scheduled purge jobs run nightly via pg_cron"
          />
          <CardBody>
            <p className="text-small text-ink-300 leading-relaxed">
              User data export requests are queued in{" "}
              <code className="font-mono text-accent">dpdp_export_jobs</code>.
              Purge-after timestamps are set 30 days from request. All PII
              columns (email, phone, resume_text) are nulled on soft-delete.
              Audit trail in{" "}
              <code className="font-mono text-accent">consent_log</code>.
            </p>
          </CardBody>
        </Card>

      </div>
    </main>
  );
}
