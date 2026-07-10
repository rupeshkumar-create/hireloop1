"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ExternalLink, Kanban, Loader2 } from "@/components/brand/icons";
import { AddExternalCandidateForm } from "@/components/recruiter/AddExternalCandidateForm";
import { RecruiterNudgesPanel } from "@/components/recruiter/RecruiterNudgesPanel";
import { Badge, Button, Card, CardBody, EmptyState } from "@/components/ui";
import { ScoreDot } from "@/components/ui/ScoreDot";
import { RoleWorkspaceTabs } from "@/components/recruiter/RoleWorkspaceTabs";
import {
  fetchPipeline,
  getRole,
  movePipelineCandidate,
  type PipelineRow,
  type RecruiterRole,
} from "@/lib/api/recruiter";

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

const NEXT_STAGE: Partial<Record<string, string>> = {
  search: "shortlisted",
  shortlisted: "intro_requested",
  intro_requested: "intro_made",
  intro_made: "interview",
  interview: "offer",
  offer: "hired",
};

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const [role, setRole] = useState<RecruiterRole | null>(null);
  const [rows, setRows] = useState<PipelineRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [moving, setMoving] = useState<string | null>(null);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, pipeline] = await Promise.all([getRole(id), fetchPipeline(id)]);
      setRole(r);
      setRows(pipeline);
      const drafts: Record<string, string> = {};
      for (const row of pipeline) {
        if (row.notes) drafts[row.id] = row.notes;
      }
      setNoteDrafts(drafts);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void load();
    }, 30_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [load]);

  async function advance(pipelineId: string, stage: string) {
    setMoving(pipelineId);
    try {
      await movePipelineCandidate(id, pipelineId, { stage });
      await load();
    } finally {
      setMoving(null);
    }
  }

  async function saveNotes(pipelineId: string) {
    setMoving(pipelineId);
    try {
      await movePipelineCandidate(id, pipelineId, {
        notes: noteDrafts[pipelineId] ?? "",
      });
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
      <RoleWorkspaceTabs
        roleId={id}
        active="pipeline"
        title={role?.title ?? null}
        publicRoleUrl={role?.public_role_url ?? null}
      />
      <header className="shrink-0 border-b border-ink-100 px-4 py-3">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="text-h3 font-semibold text-ink-900 truncate">
              {role?.title ?? "Pipeline"}
            </h1>
            <p className="text-micro text-ink-500">
              {rows.length} candidate{rows.length !== 1 ? "s" : ""} across stages
            </p>
          </div>
          <Link href={`/recruiter/roles/${id}/ops`}>
            <Button variant="ghost" size="sm">
              Add external
            </Button>
          </Link>
        </div>
      </header>

      <div className="max-w-5xl mx-auto w-full px-4 py-4">
        <RecruiterNudgesPanel roleId={id} compact />
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-auto p-4">
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-ink-300" />
          </div>
        ) : rows.length === 0 ? (
          <div className="max-w-md mx-auto space-y-6">
            <EmptyState
              icon={<Kanban strokeWidth={1.5} />}
              title="No candidates in pipeline"
              description="Run a Nitya search, add external profiles, or share your public role link for inbound applicants."
              action={
                <Link href={`/recruiter/roles/${id}/intake`}>
                  <Button variant="primary" size="sm">
                    Open Nitya chat
                  </Button>
                </Link>
              }
            />
            <AddExternalCandidateForm roleId={id} onAdded={() => void load()} />
          </div>
        ) : (
          <div className="max-w-5xl mx-auto grid gap-4 md:grid-cols-3 lg:grid-cols-4">
            {grouped.map(({ stage, label, items }) => (
              <section key={stage} className="min-w-[220px]">
                <div className="flex items-center justify-between mb-2 px-1">
                  <h2 className="text-small font-semibold text-ink-800">{label}</h2>
                  <Badge tone="muted">{items.length}</Badge>
                </div>
                <div className="space-y-2">
                  {items.map((row) => {
                    const next = NEXT_STAGE[stage];
                    return (
                      <Card key={row.id}>
                        <CardBody className="space-y-2 !p-3">
                          <div className="flex items-start justify-between gap-2">
                            <p className="text-small font-medium text-ink-900 truncate">
                              {row.display_name}
                            </p>
                            {row.source_type === "inbound" && (
                              <Badge tone="accent" className="shrink-0 text-[10px]">
                                Inbound
                              </Badge>
                            )}
                          </div>
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
                          {row.skills_gap && row.skills_gap.length > 0 && (
                            <p className="text-micro text-ink-500 line-clamp-2">
                              Gaps: {row.skills_gap.slice(0, 3).join(", ")}
                            </p>
                          )}
                          <textarea
                            value={noteDrafts[row.id] ?? ""}
                            onChange={(e) =>
                              setNoteDrafts((d) => ({ ...d, [row.id]: e.target.value }))
                            }
                            placeholder="Notes…"
                            rows={2}
                            className="w-full rounded border border-ink-100 bg-paper-0 px-2 py-1 text-micro text-ink-800 resize-none"
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            className="w-full"
                            loading={moving === row.id}
                            onClick={() => void saveNotes(row.id)}
                          >
                            Save notes
                          </Button>
                          {stage === "interview" && role?.calendly_url && (
                            <a
                              href={role.calendly_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center justify-center gap-1 text-micro text-accent hover:underline"
                            >
                              Schedule interview
                              <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                            </a>
                          )}
                          {next && (
                            <Button
                              variant="secondary"
                              size="sm"
                              className="w-full"
                              loading={moving === row.id}
                              onClick={() => void advance(row.id, next)}
                            >
                              → {STAGE_LABEL[next]}
                            </Button>
                          )}
                        </CardBody>
                      </Card>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
