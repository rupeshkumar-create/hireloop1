"use client";

import { useState } from "react";
import { UserPlus } from "@/components/brand/icons";
import { Button, Card, CardBody, Field, Input } from "@/components/ui";
import { addExternalApplicant } from "@/lib/api/recruiter";

export function AddExternalCandidateForm({
  roleId,
  onAdded,
}: {
  roleId: string;
  onAdded?: () => void;
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit() {
    if (!fullName.trim()) {
      setError("Name is required");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await addExternalApplicant(roleId, {
        full_name: fullName.trim(),
        email: email.trim() || undefined,
        linkedin_url: linkedin.trim() || undefined,
        resume: file ?? undefined,
      });
      setSuccess(
        `${res.full_name} added — match score ${Math.round((res.match_score ?? 0) * 100)}%`,
      );
      setFullName("");
      setEmail("");
      setLinkedin("");
      setFile(null);
      onAdded?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-center gap-2">
          <UserPlus className="h-4 w-4 text-accent" strokeWidth={1.5} />
          <h3 className="text-small font-semibold text-ink-900">Add external candidate</h3>
        </div>
        <p className="text-micro text-ink-500">
          Upload a resume or paste a LinkedIn URL — Nitya scores them against your brief.
        </p>
        <Field label="Full name" htmlFor="ext-name">
          <Input id="ext-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </Field>
        <Field label="Email" htmlFor="ext-email">
          <Input id="ext-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="LinkedIn URL" htmlFor="ext-li">
          <Input id="ext-li" value={linkedin} onChange={(e) => setLinkedin(e.target.value)} />
        </Field>
        <Field label="Resume (PDF/DOCX)" htmlFor="ext-resume">
          <input
            id="ext-resume"
            type="file"
            accept=".pdf,.doc,.docx"
            className="text-micro text-ink-700"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>
        {error && <p className="text-micro text-destructive">{error}</p>}
        {success && <p className="text-micro text-success">{success}</p>}
        <Button variant="primary" size="sm" loading={loading} onClick={() => void submit()}>
          Add & score
        </Button>
      </CardBody>
    </Card>
  );
}
