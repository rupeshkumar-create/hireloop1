"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Calendar, Loader2, RefreshCw } from "@/components/brand/icons";
import { AddExternalCandidateForm } from "@/components/recruiter/AddExternalCandidateForm";
import { RecruiterNudgesPanel } from "@/components/recruiter/RecruiterNudgesPanel";
import { RoleWorkspaceTabs } from "@/components/recruiter/RoleWorkspaceTabs";
import { Button, Card, CardBody, Field, Input } from "@/components/ui";
import {
  fetchInterviewKit,
  getRole,
  updateRole,
  type InterviewKit,
  type RecruiterRole,
} from "@/lib/api/recruiter";

export default function RoleOpsPage() {
  const { id } = useParams<{ id: string }>();
  const [role, setRole] = useState<RecruiterRole | null>(null);
  const [kit, setKit] = useState<InterviewKit | null>(null);
  const [calendly, setCalendly] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingCal, setSavingCal] = useState(false);
  const [loadingKit, setLoadingKit] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await getRole(id);
      setRole(r);
      setCalendly(r.calendly_url || "");
      if (r.interview_kit) setKit(r.interview_kit as InterviewKit);
      else {
        const k = await fetchInterviewKit(id);
        setKit(k.kit);
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveCalendly() {
    setSavingCal(true);
    try {
      const updated = await updateRole(id, { calendly_url: calendly.trim() || undefined });
      setRole(updated);
    } finally {
      setSavingCal(false);
    }
  }

  async function refreshKit() {
    setLoadingKit(true);
    try {
      const k = await fetchInterviewKit(id, true);
      setKit(k.kit);
    } finally {
      setLoadingKit(false);
    }
  }

  return (
    <div className="flex flex-col min-h-screen bg-paper-0">
      <RoleWorkspaceTabs
        roleId={id}
        active="ops"
        title={role?.title ?? null}
        publicRoleUrl={role?.public_role_url ?? null}
      />
      <div className="max-w-2xl mx-auto w-full px-4 py-8 space-y-6">
        <div>
          <h1 className="text-h2 font-semibold text-ink-900">Hiring ops</h1>
          <p className="text-small text-ink-500">
            Interview plan, scheduling, triage, and nudges — run the process, not just search.
          </p>
        </div>

        <RecruiterNudgesPanel roleId={id} />

        <Card>
          <CardBody className="space-y-3">
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4 text-accent" strokeWidth={1.5} />
              <h2 className="text-small font-semibold text-ink-900">Interview scheduling</h2>
            </div>
            <p className="text-micro text-ink-500">
              Calendly or Google Calendar link — shown on pipeline cards at Interview stage.
            </p>
            <Field label="Scheduling URL" htmlFor="calendly">
              <Input
                id="calendly"
                value={calendly}
                onChange={(e) => setCalendly(e.target.value)}
                placeholder="https://calendly.com/you/30min"
              />
            </Field>
            <Button variant="secondary" size="sm" loading={savingCal} onClick={() => void saveCalendly()}>
              Save link
            </Button>
          </CardBody>
        </Card>

        <AddExternalCandidateForm roleId={id} />

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-ink-300" />
          </div>
        ) : kit ? (
          <Card>
            <CardBody className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-h3 font-semibold text-ink-900">Interview kit</h2>
                <Button
                  variant="ghost"
                  size="sm"
                  loading={loadingKit}
                  leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
                  onClick={() => void refreshKit()}
                >
                  Regenerate
                </Button>
              </div>
              <p className="text-micro text-ink-600">{kit.summary}</p>
              {kit.stages.map((stage) => (
                <section key={stage.name} className="space-y-2">
                  <h3 className="text-small font-semibold text-ink-800">
                    {stage.name}{" "}
                    <span className="font-normal text-ink-500">({stage.duration_minutes} min)</span>
                  </h3>
                  <p className="text-micro text-ink-500">{stage.goal}</p>
                  <ul className="list-disc pl-5 space-y-1">
                    {stage.questions.map((q) => (
                      <li key={q} className="text-micro text-ink-700">
                        {q}
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
              {kit.red_flags.length > 0 && (
                <section>
                  <h3 className="text-small font-semibold text-ink-800 mb-2">Red flags</h3>
                  <ul className="list-disc pl-5 text-micro text-ink-600 space-y-1">
                    {kit.red_flags.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </section>
              )}
            </CardBody>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
