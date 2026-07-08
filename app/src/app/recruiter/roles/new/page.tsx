"use client";

/**
 * New role — structured form (default) + optional Nitya chat path.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Briefcase,
  LinkIcon,
  MessageCircle,
} from "@/components/brand/icons";
import {
  createRole,
  importRoleFromUrl,
  listRoles,
  type RoleListItem,
} from "@/lib/api/recruiter";
import { getCachedProfile } from "@/lib/api/profile";
import { marketByCode, type MarketCode } from "@/lib/markets";
import { compFieldLabel } from "@/lib/salary";
import { Button, Card, CardBody, CardHeader, Field, Input } from "@/components/ui";

const REMOTE_OPTIONS = [
  { value: "", label: "Not specified" },
  { value: "onsite", label: "Onsite" },
  { value: "hybrid", label: "Hybrid" },
  { value: "remote", label: "Remote" },
  { value: "flex", label: "Flexible" },
];

export default function NewRolePage() {
  const router = useRouter();
  const [market, setMarket] = useState<MarketCode>("IN");
  const [title, setTitle] = useState("");
  const [jd, setJd] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [compMin, setCompMin] = useState("");
  const [compMax, setCompMax] = useState("");
  const [city, setCity] = useState("");
  const [remote, setRemote] = useState("");
  const [seniority, setSeniority] = useState("");
  const [duplicateId, setDuplicateId] = useState("");
  const [importUrl, setImportUrl] = useState("");
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const [pastRoles, setPastRoles] = useState<RoleListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const m = getCachedProfile()?.user?.market;
    if (m) setMarket(marketByCode(m).code);
    listRoles()
      .then(setPastRoles)
      .catch(() => setPastRoles([]));
  }, []);

  async function handleImportUrl() {
    const url = importUrl.trim();
    if (!url) return;
    setImporting(true);
    setError(null);
    setImportWarnings([]);
    try {
      const res = await importRoleFromUrl(url);
      if (res.title) setTitle(res.title);
      if (res.jd_text) setJd(res.jd_text);
      if (res.company_name) setCompanyName(res.company_name);
      if (res.comp_min_lpa != null) setCompMin(String(res.comp_min_lpa));
      if (res.comp_max_lpa != null) setCompMax(String(res.comp_max_lpa));
      if (res.location_city) setCity(res.location_city);
      if (res.remote_policy) setRemote(res.remote_policy);
      if (res.seniority) setSeniority(res.seniority);
      setImportWarnings(res.warnings || []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setImporting(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await createRole({
        title: title.trim(),
        jd_text: jd.trim() || null,
        company_name: companyName.trim() || null,
        duplicate_from_role_id: duplicateId || null,
        comp_min_lpa: compMin ? Number(compMin) : null,
        comp_max_lpa: compMax ? Number(compMax) : null,
        location_city: city.trim() || null,
        remote_policy: remote || null,
        seniority: seniority || null,
      });

      if (res.skip_intake || (jd.trim().length >= 40)) {
        router.push(`/recruiter/roles/${res.role_id}/brief`);
      } else {
        router.push(`/recruiter/roles/${res.role_id}/intake`);
      }
    } catch (err) {
      setError((err as Error).message);
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-paper-0 px-4 py-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <Link
          href="/recruiter"
          className="inline-flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          Back to recruiter home
        </Link>

        <div className="grid lg:grid-cols-[1fr_280px] gap-6 items-start">
          <Card className="shadow-2">
            <CardHeader
              title="Create a new role"
              description="Fill the essentials — we'll extract the brief from your JD instantly"
              action={
                <div className="w-10 h-10 rounded-full bg-ink-900 flex items-center justify-center">
                  <Briefcase className="h-5 w-5 text-paper-0" strokeWidth={1.5} />
                </div>
              }
            />

            <CardBody>
              <form onSubmit={handleCreate} className="space-y-4">
                {pastRoles.length > 0 && (
                  <Field
                    label="Duplicate from last role"
                    htmlFor="duplicate-role"
                    helper="Copy comp, location, and evaluation from a previous role"
                  >
                    <select
                      id="duplicate-role"
                      value={duplicateId}
                      onChange={(e) => setDuplicateId(e.target.value)}
                      className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-body text-ink-900 focus:outline-none focus:border-ink-300"
                    >
                      <option value="">Start fresh</option>
                      {pastRoles.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.title}
                          {r.location_city ? ` · ${r.location_city}` : ""}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}

                <Field
                  label="Role title"
                  htmlFor="role-title"
                  helper="e.g. Senior Backend Engineer"
                >
                  <Input
                    id="role-title"
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Senior Backend Engineer"
                    required
                    autoFocus
                  />
                </Field>

                <Field
                  label="Company"
                  htmlFor="role-company"
                  helper="Auto-filled from the job link when available"
                >
                  <Input
                    id="role-company"
                    type="text"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="Acme India Pvt Ltd"
                  />
                </Field>

                <Field
                  label="Import from URL"
                  htmlFor="jd-url"
                  helper="Paste a public job link — Greenhouse, Lever, or any career page. We'll crawl it and fill the form."
                >
                  <div className="flex gap-2">
                    <Input
                      id="jd-url"
                      type="url"
                      value={importUrl}
                      onChange={(e) => setImportUrl(e.target.value)}
                      placeholder="https://boards.greenhouse.io/… or https://jobs.lever.co/…"
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      loading={importing}
                      disabled={!importUrl.trim()}
                      onClick={() => void handleImportUrl()}
                      leftIcon={<LinkIcon className="h-4 w-4" strokeWidth={1.5} />}
                    >
                      Import
                    </Button>
                  </div>
                </Field>

                {importWarnings.length > 0 && (
                  <ul className="text-small text-ink-600 bg-paper-1 border border-ink-100 rounded-md px-3 py-2 space-y-1">
                    {importWarnings.map((w) => (
                      <li key={w}>• {w}</li>
                    ))}
                  </ul>
                )}

                <Field
                  label="Job description"
                  htmlFor="jd-text"
                  helper="Paste JD or import from URL — we'll extract the brief instantly"
                >
                  <textarea
                    id="jd-text"
                    value={jd}
                    onChange={(e) => setJd(e.target.value)}
                    placeholder="Paste job description here…"
                    rows={8}
                    className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-body text-ink-900 placeholder:text-ink-300 focus:outline-none focus:border-ink-300 focus:ring-2 focus:ring-accent/15 resize-y min-h-[160px]"
                  />
                </Field>

                <div className="grid sm:grid-cols-2 gap-3">
                  <Field label={compFieldLabel(market, "min")} htmlFor="comp-min">
                    <Input
                      id="comp-min"
                      type="number"
                      min={0}
                      value={compMin}
                      onChange={(e) => setCompMin(e.target.value)}
                      placeholder="25"
                    />
                  </Field>
                  <Field label={compFieldLabel(market, "max")} htmlFor="comp-max">
                    <Input
                      id="comp-max"
                      type="number"
                      min={0}
                      value={compMax}
                      onChange={(e) => setCompMax(e.target.value)}
                      placeholder="40"
                    />
                  </Field>
                </div>

                <div className="grid sm:grid-cols-2 gap-3">
                  <Field label="City" htmlFor="role-city">
                    <Input
                      id="role-city"
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      placeholder="Bengaluru"
                    />
                  </Field>
                  <Field label="Seniority" htmlFor="role-seniority">
                    <select
                      id="role-seniority"
                      value={seniority}
                      onChange={(e) => setSeniority(e.target.value)}
                      className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-body text-ink-900 focus:outline-none focus:border-ink-300"
                    >
                      <option value="">Not specified</option>
                      <option value="junior">Junior</option>
                      <option value="mid">Mid</option>
                      <option value="senior">Senior</option>
                      <option value="lead">Lead</option>
                      <option value="manager">Manager</option>
                      <option value="director">Director</option>
                    </select>
                  </Field>
                </div>

                <Field label="Work mode" htmlFor="role-remote">
                  <select
                    id="role-remote"
                    value={remote}
                    onChange={(e) => setRemote(e.target.value)}
                    className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-body text-ink-900 focus:outline-none focus:border-ink-300"
                  >
                    {REMOTE_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </Field>

                {error && (
                  <p className="text-small text-destructive bg-destructive-bg rounded-md px-3 py-2">
                    {error}
                  </p>
                )}

                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  fullWidth
                  loading={loading}
                  disabled={!title.trim()}
                  rightIcon={!loading && <ArrowRight className="h-4 w-4" strokeWidth={1.5} />}
                >
                  {loading ? "Creating role…" : "Create role"}
                </Button>
              </form>
            </CardBody>
          </Card>

          <aside className="space-y-4">
            <Card className="border border-ink-100">
              <CardBody className="space-y-3">
                <div className="flex items-center gap-2">
                  <MessageCircle className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                  <p className="text-body font-medium text-ink-900">Or talk to Nitya</p>
                </div>
                <p className="text-small text-ink-500">
                  Skip the form and describe a messy role in chat — max 3 questions,
                  then search runs on your JD.
                </p>
                <p className="text-micro text-ink-400">
                  Create with title only (no JD) to open Nitya intake directly.
                </p>
              </CardBody>
            </Card>

            <p className="text-micro text-ink-500">
              Target: candidates in under 2 minutes. Paste JD → brief card → Start search.
            </p>
          </aside>
        </div>
      </div>
    </main>
  );
}
