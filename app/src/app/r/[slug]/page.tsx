"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Briefcase, Building2, MapPin } from "@/components/brand/icons";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { Card, CardBody } from "@/components/ui";
import { createClient } from "@/lib/supabase/client";
import { persistPostAuthRedirect } from "@/lib/auth/post-auth-redirect";
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

function jobsDestination(role: PublicRole): string {
  if (role.job_id) {
    return `/jobs/${encodeURIComponent(role.job_id)}`;
  }
  return "/dashboard?panel=jobs";
}

function candidateSignupHref(role: PublicRole, destination: string): string {
  const qs = new URLSearchParams();
  qs.set("role", "candidate");
  qs.set("from", destination);
  if (role.job_id) qs.set("job_id", role.job_id);
  qs.set("role_slug", role.slug);
  return `/signup?${qs.toString()}`;
}

export default function PublicRolePage() {
  const params = useParams();
  const slug = typeof params.slug === "string" ? params.slug : "";
  const [role, setRole] = useState<PublicRole | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [signedInCandidate, setSignedInCandidate] = useState(false);

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

  useEffect(() => {
    let cancelled = false;
    void createClient()
      .auth.getUser()
      .then(({ data }) => {
        if (!cancelled) setSignedInCandidate(Boolean(data.user));
      })
      .catch(() => {
        if (!cancelled) setSignedInCandidate(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const destination = useMemo(
    () => (role ? jobsDestination(role) : "/dashboard?panel=jobs"),
    [role],
  );
  const applyHref = useMemo(() => {
    if (!role) return "/signup?role=candidate";
    if (signedInCandidate) return destination;
    return candidateSignupHref(role, destination);
  }, [role, signedInCandidate, destination]);

  function handleApplyClick() {
    persistPostAuthRedirect(destination);
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

        <Card>
          <CardBody className="space-y-3">
            <h2 className="text-h3 font-semibold text-ink-900">Want this role?</h2>
            <p className="text-small text-ink-600">
              {signedInCandidate
                ? "Open the job on Hireschema to save it and request a warm intro."
                : "Create a candidate account, then open Jobs to request an intro for this role."}
            </p>
            <Link
              href={applyHref}
              onClick={handleApplyClick}
              className="inline-flex w-full items-center justify-center h-10 px-4 rounded-md bg-accent text-ink-900 text-body font-semibold hover:brightness-95 transition-colors"
            >
              Apply for this job
            </Link>
            {!signedInCandidate && (
              <p className="text-micro text-ink-500 text-center">
                Already on Hireschema?{" "}
                <Link
                  href={`/signup?mode=signin&role=candidate&from=${encodeURIComponent(destination)}`}
                  onClick={handleApplyClick}
                  className="text-accent hover:underline"
                >
                  Sign in
                </Link>
              </p>
            )}
          </CardBody>
        </Card>

        <p className="text-micro text-ink-500 text-center pt-2">
          This is a live listing from a Hireschema recruiter.
        </p>
      </main>
    </div>
  );
}
