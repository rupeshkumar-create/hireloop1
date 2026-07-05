"use client";

/**
 * Admin / Placements — P22 deferred to v2, manually managed here for first hires.
 * Records hired candidates with compensation + invoice tracking.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle, Clock } from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import { Badge, EmptyState } from "@/components/ui";

type Placement = {
  id: string;
  candidate_name: string;
  role_title: string;
  company_name: string;
  status: "pending" | "confirmed" | "invoiced" | "paid";
  placed_at: string;
  ctc_inr?: number;
};

const STATUS_BADGE: Record<
  Placement["status"],
  { tone: "muted" | "strong" | "accent"; label: string }
> = {
  pending:   { tone: "muted",   label: "Pending"   },
  confirmed: { tone: "strong",  label: "Confirmed" },
  invoiced:  { tone: "accent",  label: "Invoiced"  },
  paid:      { tone: "accent",  label: "Paid ✓"    },
};

export default function AdminPlacementsPage() {
  const [rows, setRows]     = useState<Placement[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Placement[]>("/api/v1/admin/placements")
      .then((r) => { setRows(r); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  return (
    <main className="min-h-screen bg-ink-900 text-paper-0 p-6">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center gap-3">
          <Link
            href="/admin"
            className="text-ink-500 hover:text-paper-0 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
          </Link>
          <div>
            <h1 className="text-h1 text-paper-0">Placements</h1>
            <p className="text-small text-ink-500">
              P22 (Razorpay) deferred to v2 — manual billing via this panel
            </p>
          </div>
        </div>

        {error && (
          <div className="text-destructive text-small bg-destructive-bg rounded-md px-4 py-3">
            {error}
          </div>
        )}

        {/* Table */}
        {!loading && rows.length === 0 && (
          <EmptyState
            icon={<CheckCircle strokeWidth={1.5} />}
            title="No placements yet"
            description="When a recruiter marks a candidate as 'Hired' in the pipeline, the placement record appears here."
          />
        )}

        {rows.length > 0 && (
          <div className="rounded-lg border border-ink-700 overflow-hidden">
            <table className="w-full text-small">
              <thead className="bg-ink-700">
                <tr>
                  {["Candidate", "Role", "Company", "CTC (INR)", "Date", "Status"].map((h) => (
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
                  const meta = STATUS_BADGE[r.status] ?? STATUS_BADGE.pending;
                  return (
                    <tr key={r.id} className="hover:bg-ink-700/40 transition-colors">
                      <td className="px-4 py-3 text-paper-0 font-medium">
                        {r.candidate_name}
                      </td>
                      <td className="px-4 py-3 text-ink-300">{r.role_title}</td>
                      <td className="px-4 py-3 text-ink-300">{r.company_name}</td>
                      <td className="px-4 py-3 text-paper-0">
                        {r.ctc_inr
                          ? `₹${(r.ctc_inr / 100000).toFixed(1)}L`
                          : <span className="text-ink-500">—</span>}
                      </td>
                      <td className="px-4 py-3 text-ink-500 text-micro">
                        {new Date(r.placed_at).toLocaleDateString("en-IN", {
                          day: "numeric", month: "short", year: "numeric",
                        })}
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={meta.tone}>{meta.label}</Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-12 rounded-md bg-ink-700 animate-skeleton"
              />
            ))}
          </div>
        )}

        {/* Note */}
        <div className="flex items-start gap-2 text-small text-ink-500 border border-ink-700 rounded-md px-4 py-3">
          <Clock className="h-4 w-4 shrink-0 mt-0.5" strokeWidth={1.5} />
          <p>
            Placements are created automatically when a recruiter drags a candidate
            to the <strong className="text-ink-300">Hired</strong> column in the
            pipeline view. Invoice management and Razorpay integration is v2.
          </p>
        </div>

      </div>
    </main>
  );
}
