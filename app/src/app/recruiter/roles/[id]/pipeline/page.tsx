"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Kanban, Loader2 } from "lucide-react";
import { Badge, Button, Card, CardBody, EmptyState } from "@/components/ui";
import { ScoreDot } from "@/components/ui/ScoreDot";
import { RecruiterBreadcrumbs } from "@/components/ux";
import { apiFetch } from "@/lib/api/client";
import { getRole, movePipelineCandidate, type RecruiterRole } from "@/lib/api/recruiter";

type PipelineRow = {
  id: string;
  stage: string;
  match_score: number | null;
  display_name: string;
  headline: string | null;
  current_title: string | null;
  years_experience: number | null;
  moved_at: string;
};

const STAGES = [
  "search",
  "shortlisted",
  "intro_requested",
  "intro_made",
  "interview",
  "offer",
  "hired",
] as const;

const STAGE_LABEL: Record<string, string> = {
  search: "Sourced",
  shortlisted: "Shortlisted",
  intro_requested: "Intro requested",
  intro_made: "Intro made",
  interview: "Interview",
  offer: "Offer",
  hired: "Hired",
  archived: "Archived",
};

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const [role, setRole] = useState<RecruiterRole | null>(null);
  const [rows, setRows] = useState<PipelineRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [moving, setMoving] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [r, pipeline] = await Promise.all([
        getRole(id),
        apiFetch<PipelineRow[]>(`/api/v1/recruiter/roles/${id}/pipeline`),
      ]);
      setRole(r);
      setRows(pipeline);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [id]);

  async function advance(pipelineId: string, stage: string) {
    setMoving(pipelineId);
    try {
      await movePipelineCandidate(id, pipelineId, stage);
      await load();
    } finally {
      setMoving(null);
    }
  }

  const grouped = STAGES.map((stage) => ({
    stage,
    label: STAGE_LABEL[stage],
    items: rows.filter((r) => r.stage === stage),
  }));

  return (
    <div className="flex flex-col h-full bg-paper-0">
      <header className="shrink-0 border-b border-ink-100 px-4 py-3">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <Link
            href={`/recruiter/roles/${id}/intake`}
            className="text-ink-500 hover:text-ink-900 p-1"
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
          </Link>
          <div className="flex-1 min-w-0">
            <h1 className="text-h3 font-semibold text-ink-900 truncate">
              {role?.title ?? "Pipeline"}
            </h1>
            <p className="text-micro text-ink-500">
              {rows.length} candidate{rows.length !== 1 ? "s" : ""} across stages
            </p>
          </div>
          <Link href={`/recruiter/roles/${id}/intake`}>
            <Button variant="secondary" size="sm">
              Back to Nitya
            </Button>
          </Link>
        </div>
      </header>

      <div className="flex-1 overflow-x-auto overflow-y-auto p-4">
        <RecruiterBreadcrumbs
          crumbs={[
            { label: "Inbox", href: "/recruiter/inbox" },
            { label: role?.title ?? "Role", href: `/recruiter/roles/${id}/intake` },
            { label: "Pipeline" },
          ]}
        />
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-ink-300" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Kanban strokeWidth={1.5} />}
            title="No candidates in pipeline"
            description="Ask Nitya to search for candidates on the intake chat."
            action={
              <Link href={`/recruiter/roles/${id}/intake`}>
                <Button variant="primary" size="sm">
                  Open Nitya chat
                </Button>
              </Link>
            }
          />
        ) : (
          <div className="max-w-5xl mx-auto grid gap-4 md:grid-cols-3 lg:grid-cols-4">
            {grouped.map(({ stage, label, items }) => (
              <section key={stage} className="min-w-[220px]">
                <div className="flex items-center justify-between mb-2 px-1">
                  <h2 className="text-small font-semibold text-ink-800">{label}</h2>
                  <Badge tone="muted">{items.length}</Badge>
                </div>
                <div className="space-y-2">
                  {items.map((row) => (
                    <Card key={row.id}>
                      <CardBody className="space-y-2 !p-3">
                        <p className="text-small font-medium text-ink-900 truncate">
                          {row.display_name}
                        </p>
                        <p className="text-micro text-ink-500 truncate">
                          {row.current_title ?? row.headline ?? "—"}
                        </p>
                        {row.match_score != null && (
                          <div className="flex items-center gap-2 text-micro text-ink-500">
                            <ScoreDot value={row.match_score} size="sm" />
                            {row.years_experience != null && (
                              <span>{row.years_experience}y exp</span>
                            )}
                          </div>
                        )}
                        {stage === "search" && (
                          <Button
                            variant="secondary"
                            size="sm"
                            className="w-full"
                            loading={moving === row.id}
                            onClick={() => void advance(row.id, "shortlisted")}
                          >
                            Shortlist
                          </Button>
                        )}
                        {stage === "shortlisted" && (
                          <Button
                            variant="secondary"
                            size="sm"
                            className="w-full"
                            loading={moving === row.id}
                            onClick={() => void advance(row.id, "intro_requested")}
                          >
                            Mark intro requested
                          </Button>
                        )}
                      </CardBody>
                    </Card>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
