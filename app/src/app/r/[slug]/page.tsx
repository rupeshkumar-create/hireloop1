"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Briefcase, Building2, MapPin } from "@/components/brand/icons";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { Button, Card, CardBody } from "@/components/ui";
import { formatSalaryRange } from "@/lib/salary";

type PublicRole = {
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

        {role.nice_to_haves.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-h3 font-semibold text-ink-900">Nice-to-haves</h2>
            <div className="flex flex-wrap gap-1.5">
              {role.nice_to_haves.map((s) => (
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

        <div className="rounded-xl border border-accent/30 bg-accent/5 px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-small text-ink-800">
            Interested in this role? Join Hireschema to request a warm intro.
          </p>
          <Link href="/signup?role=candidate">
            <Button variant="primary" size="sm">
              Apply via Hireschema
            </Button>
          </Link>
        </div>

        <p className="text-micro text-ink-500 text-center pt-2">
          This is a live listing from a Hireschema recruiter.
        </p>
      </main>
    </div>
  );
}
