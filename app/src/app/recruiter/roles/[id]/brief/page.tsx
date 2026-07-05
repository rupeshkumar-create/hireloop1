"use client";

/**
 * Role brief — fast path after JD paste.
 * Editable summary card + progress bar + Start search / Talk to Nitya.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  MessageCircle,
  Search,
  Sparkles,
} from "@/components/brand/icons";
import {
  formatCompRange,
  getRole,
  startRoleSearch,
  updateRole,
  type RecruiterRole,
  type RoleReadiness,
} from "@/lib/api/recruiter";
import { getCachedProfile } from "@/lib/api/profile";
import { marketByCode, type MarketCode } from "@/lib/markets";
import { compFieldLabel, profileSalaryFromStorage } from "@/lib/salary";
import { RoleReadinessBar } from "@/components/recruiter/RoleReadinessBar";
import { Button, Card, CardBody, CardHeader, Field, Input } from "@/components/ui";

export default function RoleBriefPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [role, setRole] = useState<RecruiterRole | null>(null);
  const [market, setMarket] = useState<MarketCode>("IN");
  const [readiness, setReadiness] = useState<RoleReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [hiringBrief, setHiringBrief] = useState("");
  const [mustHaves, setMustHaves] = useState("");
  const [compMin, setCompMin] = useState("");
  const [compMax, setCompMax] = useState("");
  const [city, setCity] = useState("");
  const [remote, setRemote] = useState("");

  const hydrate = useCallback(
    (r: RecruiterRole) => {
      setRole(r);
      setTitle(r.title);
      setHiringBrief(r.hiring_brief || "");
      setMustHaves((r.must_haves || []).join(", "));
      setCompMin(profileSalaryFromStorage(r.comp_min, market));
      setCompMax(profileSalaryFromStorage(r.comp_max, market));
      setCity(r.location_city || "");
      setRemote(r.remote_policy || "");
      if (r.readiness) setReadiness(r.readiness);
    },
    [market],
  );

  useEffect(() => {
    const m = getCachedProfile()?.user?.market;
    if (m) setMarket(marketByCode(m).code);
  }, []);

  useEffect(() => {
    getRole(id)
      .then(hydrate)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [id, hydrate]);

  async function saveEdits(): Promise<boolean> {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: title.trim(),
        hiring_brief: hiringBrief.trim(),
        must_haves: mustHaves
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        comp_min_lpa: compMin ? Number(compMin) : undefined,
        comp_max_lpa: compMax ? Number(compMax) : undefined,
        location_city: city.trim() || undefined,
        remote_policy: remote || undefined,
      };
      const updated = await updateRole(id, payload);
      hydrate(updated);
      if (updated.readiness) setReadiness(updated.readiness);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function handleStartSearch() {
    setSearching(true);
    setError(null);
    const saved = await saveEdits();
    if (!saved) {
      setSearching(false);
      return;
    }
    try {
      await startRoleSearch(id);
      router.push(`/recruiter/roles/${id}/intake`);
    } catch (e) {
      setError((e as Error).message);
      setSearching(false);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-paper-0 flex items-center justify-center">
        <p className="text-small text-ink-500">Loading brief…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-paper-0 px-4 py-8">
      <div className="max-w-2xl mx-auto space-y-6">
        <Link
          href="/recruiter"
          className="inline-flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          Back to recruiter home
        </Link>

        <div className="space-y-1">
          <h1 className="text-h2 font-semibold text-ink-900">Role brief</h1>
          <p className="text-small text-ink-500">
            Review what we extracted from your JD — edit anything, then start search.
          </p>
        </div>

        {readiness && <RoleReadinessBar readiness={readiness} />}

        <Card className="shadow-2">
          <CardHeader
            title="Hiring summary"
            description="Auto-extracted from your JD — assumptions are shown below"
            action={
              <div className="w-9 h-9 rounded-full bg-accent/10 flex items-center justify-center">
                <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.5} />
              </div>
            }
          />
          <CardBody className="space-y-4">
            <Field label="Title" htmlFor="brief-title">
              <Input
                id="brief-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>

            <Field label="Internal brief" htmlFor="brief-text">
              <textarea
                id="brief-text"
                value={hiringBrief}
                onChange={(e) => setHiringBrief(e.target.value)}
                rows={4}
                className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-body text-ink-900 focus:outline-none focus:border-ink-300 focus:ring-2 focus:ring-accent/15 resize-y"
              />
            </Field>

            <Field
              label="Must-haves"
              htmlFor="brief-must"
              helper="Comma-separated skills or requirements"
            >
              <Input
                id="brief-must"
                value={mustHaves}
                onChange={(e) => setMustHaves(e.target.value)}
                placeholder="Python, PostgreSQL, 5+ years…"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label={compFieldLabel(market, "min")} htmlFor="comp-min">
                <Input
                  id="comp-min"
                  type="number"
                  min={0}
                  value={compMin}
                  onChange={(e) => setCompMin(e.target.value)}
                  placeholder="e.g. 25"
                />
              </Field>
              <Field label={compFieldLabel(market, "max")} htmlFor="comp-max">
                <Input
                  id="comp-max"
                  type="number"
                  min={0}
                  value={compMax}
                  onChange={(e) => setCompMax(e.target.value)}
                  placeholder="e.g. 40"
                />
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label="City" htmlFor="brief-city">
                <Input
                  id="brief-city"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  placeholder="Bengaluru"
                />
              </Field>
              <Field label="Work mode" htmlFor="brief-remote">
                <select
                  id="brief-remote"
                  value={remote}
                  onChange={(e) => setRemote(e.target.value)}
                  className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-body text-ink-900 focus:outline-none focus:border-ink-300"
                >
                  <option value="">Not set</option>
                  <option value="onsite">Onsite</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="remote">Remote</option>
                  <option value="flex">Flexible</option>
                </select>
              </Field>
            </div>

            {role && (
              <p className="text-micro text-ink-500 bg-paper-1 rounded-md px-3 py-2">
                Current comp:{" "}
                {formatCompRange(role.comp_min, role.comp_max, { market })}
                {role.candidate_pitch && (
                  <>
                    {" · "}
                    Pitch: {role.candidate_pitch}
                  </>
                )}
              </p>
            )}

            {error && (
              <p className="text-small text-destructive bg-destructive-bg rounded-md px-3 py-2">
                {error}
              </p>
            )}

            <div className="flex flex-col sm:flex-row gap-3 pt-2">
              <Button
                variant="primary"
                size="lg"
                fullWidth
                loading={searching}
                disabled={searching || saving}
                onClick={() => void handleStartSearch()}
                leftIcon={<Search className="h-4 w-4" strokeWidth={1.5} />}
                rightIcon={
                  !searching && <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
                }
              >
                Start search
              </Button>
              <Link href={`/recruiter/roles/${id}/intake`} className="flex-1">
                <Button
                  variant="secondary"
                  size="lg"
                  fullWidth
                  leftIcon={<MessageCircle className="h-4 w-4" strokeWidth={1.5} />}
                >
                  Talk to Nitya to refine
                </Button>
              </Link>
            </div>

            <Button
              variant="ghost"
              size="sm"
              loading={saving}
              disabled={saving || searching}
              onClick={() => void saveEdits()}
            >
              Save edits only
            </Button>
          </CardBody>
        </Card>
      </div>
    </main>
  );
}
