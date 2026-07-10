"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Briefcase, Building2, CheckCircle, MapPin } from "@/components/brand/icons";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { Button, Card, CardBody, Field, Input } from "@/components/ui";
import { formatSalaryRange } from "@/lib/salary";

type PublicRole = {
  role_id: string;
  job_id: string | null;
  slug: string;
  title: string;
  company_name: string | null;
  company_logo_url: string | null;
  description: string | null;
  comp_min: number | null;
  comp_max: number | null;
  location: string | null;
  remote_policy: string | null;
  must_haves: string[];
  nice_to_haves: string[];
  status: string;
  market: string;
  updated_at: string | null;
};

export default function PublicRolePage() {
  const params = useParams();
  const slug = typeof params.slug === "string" ? params.slug : "";
  const [role, setRole] = useState<PublicRole | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [resume, setResume] = useState<File | null>(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [matchScore, setMatchScore] = useState<number | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    void fetch(`${getApiBaseUrl()}/api/v1/public/roles/${encodeURIComponent(slug)}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            (body as { detail?: string }).detail ?? "Role not found"
          );
        }
        return res.json() as Promise<PublicRole>;
      })
      .then(setRole)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, [slug]);

  async function submitApplication(e: React.FormEvent) {
    e.preventDefault();
    if (!resume || !fullName.trim() || !email.trim()) {
      setApplyError("Name, email, and resume are required.");
      return;
    }
    setApplying(true);
    setApplyError(null);
    try {
      const form = new FormData();
      form.set("full_name", fullName.trim());
      form.set("email", email.trim());
      form.set("resume", resume);
      const res = await fetch(
        `${getApiBaseUrl()}/api/v1/public/roles/${encodeURIComponent(slug)}/apply`,
        { method: "POST", body: form },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error((body as { detail?: string }).detail ?? "Application failed");
      }
      setApplied(true);
      setMatchScore((body as { match_score?: number }).match_score ?? null);
    } catch (err) {
      setApplyError((err as Error).message);
    } finally {
      setApplying(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-paper-0 flex items-center justify-center text-ink-500 text-small">
        Loading role…
      </div>
    );
  }

  if (error || !role) {
    return (
      <div className="min-h-screen bg-paper-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-body text-ink-700">{error ?? "Role unavailable"}</p>
        <Link href="/" className="text-small text-accent hover:underline">
          Go to Hireschema
        </Link>
      </div>
    );
  }

  const compLabel = formatSalaryRange(role.comp_min, role.comp_max, {
    market: role.market,
  });

  const signupHref = role.job_id
    ? `/signup?role=candidate&job_id=${encodeURIComponent(role.job_id)}&role_slug=${encodeURIComponent(slug)}`
    : `/signup?role=candidate&role_slug=${encodeURIComponent(slug)}`;

  return (
    <div className="min-h-screen bg-paper-0">
      <header className="border-b border-ink-100 bg-paper-1">
        <div className="max-w-2xl mx-auto px-5 py-4 flex items-center justify-between">
          <Link href="/" className="text-small font-semibold text-ink-900">
            Hireschema
          </Link>
          <span className="text-micro text-ink-500">Open role</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-8 space-y-6">
        <div className="space-y-3">
          <h1 className="text-h1 font-semibold text-ink-900">{role.title}</h1>
          <div className="flex flex-wrap gap-3 text-micro text-ink-500">
            {role.company_name && (
              <span className="inline-flex items-center gap-1">
                <Building2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                {role.company_name}
              </span>
            )}
            {role.location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" strokeWidth={1.5} />
                {role.location}
              </span>
            )}
            {role.remote_policy && (
              <span className="inline-flex items-center gap-1">
                <Briefcase className="h-3.5 w-3.5" strokeWidth={1.5} />
                {role.remote_policy}
              </span>
            )}
            {compLabel && <span>{compLabel}</span>}
          </div>
        </div>

        {role.description && (
          <Card>
            <CardBody>
              <p className="text-small text-ink-700 leading-relaxed whitespace-pre-wrap">
                {role.description}
              </p>
            </CardBody>
          </Card>
        )}

        {role.must_haves.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-h3 font-semibold text-ink-900">Must-haves</h2>
            <div className="flex flex-wrap gap-1.5">
              {role.must_haves.map((s) => (
                <span
                  key={s}
                  className="rounded-full border border-ink-100 bg-paper-1 px-2.5 py-1 text-micro text-ink-700"
                >
                  {s}
                </span>
              ))}
            </div>
          </section>
        )}

        {applied ? (
          <div className="rounded-xl border border-success/30 bg-success/5 px-5 py-4 space-y-2">
            <div className="flex items-center gap-2 text-small font-medium text-ink-900">
              <CheckCircle className="h-4 w-4 text-success" strokeWidth={1.5} />
              Application submitted
            </div>
            <p className="text-small text-ink-700">
              The hiring team will review your profile against this role.
              {matchScore != null && (
                <> Initial fit score: {Math.round(matchScore * 100)}%.</>
              )}
            </p>
            <Link href={signupHref} className="text-small text-accent hover:underline inline-block">
              Join Hireschema for warm intros and more roles →
            </Link>
          </div>
        ) : (
          <Card>
            <CardBody>
              <h2 className="text-h3 font-semibold text-ink-900 mb-1">Apply to this role</h2>
              <p className="text-micro text-ink-500 mb-4">
                Upload your resume — we score it against the hiring brief instantly.
              </p>
              <form onSubmit={(e) => void submitApplication(e)} className="space-y-3">
                <Field label="Full name" htmlFor="apply-name">
                  <Input
                    id="apply-name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                  />
                </Field>
                <Field label="Email" htmlFor="apply-email">
                  <Input
                    id="apply-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </Field>
                <Field label="Resume (PDF or DOCX)" htmlFor="apply-resume">
                  <input
                    id="apply-resume"
                    type="file"
                    accept=".pdf,.doc,.docx"
                    required
                    className="text-micro text-ink-700"
                    onChange={(e) => setResume(e.target.files?.[0] ?? null)}
                  />
                </Field>
                {applyError && (
                  <p className="text-micro text-destructive">{applyError}</p>
                )}
                <Button type="submit" variant="primary" size="sm" loading={applying} fullWidth>
                  Submit application
                </Button>
              </form>
              <p className="text-micro text-ink-500 mt-4 text-center">
                Already on Hireschema?{" "}
                <Link href={signupHref} className="text-accent hover:underline">
                  Sign in to request a warm intro
                </Link>
              </p>
            </CardBody>
          </Card>
        )}

        <p className="text-micro text-ink-500 text-center pt-2">
          This is a live listing from a Hireschema recruiter.
        </p>
      </main>
    </div>
  );
}
