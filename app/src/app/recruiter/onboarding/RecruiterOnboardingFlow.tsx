"use client";

/**
 * Recruiter onboarding — one screen, two fields, one click.
 *
 * Company + what you're hiring for. Everything else (your title, JD, comp,
 * must-haves) is refined later in the role's Nitya intake chat, which is
 * where we land on finish — a live conversation about the role beats an
 * empty inbox. Distinct from candidate onboarding (Aarya CV wizard).
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Building2,
  MapPin,
  Briefcase,
  LinkIcon,
} from "@/components/brand/icons";
import { NityaFace } from "@/components/nitya/NityaFace";
import { Button, Field, Input } from "@/components/ui";
import { fetchAuthMe } from "@/lib/api/auth";
import {
  createRole,
  fetchRecruiterProfile,
  importRoleFromUrl,
  updateRecruiterProfile,
} from "@/lib/api/recruiter";

export function RecruiterOnboardingFlow() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [roleCity, setRoleCity] = useState("");
  const [mode, setMode] = useState<"form" | "import">("form");
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const roleCheckDone = useRef(false);

  useEffect(() => {
    if (roleCheckDone.current) return;
    roleCheckDone.current = true;
    void fetchAuthMe()
      .then((me) => {
        if (me.role === "candidate") {
          router.replace("/onboarding");
        }
      })
      .catch(() => {
        /* server page may still redirect */
      });
  }, [router]);

  useEffect(() => {
    fetchRecruiterProfile()
      .then((p) => {
        if (p.onboarding_complete) {
          router.replace("/recruiter");
          return;
        }
        setCompanyName(p.company_name === "My Company" ? "" : (p.company_name ?? ""));
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [router]);

  async function handleImportFromUrl() {
    const url = importUrl.trim();
    if (!url || importing || saving) return;
    setImporting(true);
    setError(null);
    try {
      const res = await importRoleFromUrl(url);
      if (res.title) setRoleTitle(res.title);
      if (res.location_city) setRoleCity(res.location_city);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setImporting(false);
    }
  }

  async function finish() {
    if (saving) return;
    if (!companyName.trim()) {
      setError("Company name is required.");
      return;
    }
    if (!roleTitle.trim()) {
      setError("Tell Nitya what role you're hiring for.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateRecruiterProfile({
        company_name: companyName.trim(),
        onboarding_complete: true,
      });
      const created = await createRole({
        title: roleTitle.trim().slice(0, 120),
        location_city: roleCity.trim() || undefined,
      });
      // Land in the role's Nitya intake chat — the brief conversation starts
      // immediately instead of an empty inbox.
      router.push(
        created.role_id ? `/recruiter/roles/${created.role_id}/intake` : "/recruiter",
      );
    } catch (e) {
      setError((e as Error).message);
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper-0 text-ink-500 text-small">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper-0 flex items-center px-6 py-12">
      <div className="max-w-md mx-auto w-full space-y-6">
        <div className="flex items-start gap-3">
          <NityaFace size="md" />
          <div className="bg-paper-1 rounded-lg rounded-tl-sm px-5 py-4 shadow-1 border border-accent/20">
            <p className="text-body text-ink-900 leading-relaxed">
              Hi — I&apos;m Nitya. Two quick things and we&apos;ll start finding
              candidates for you.
            </p>
          </div>
        </div>

        <div className="space-y-4 rounded-lg border border-ink-100 bg-paper-1 p-5 shadow-1">
          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={mode === "form" ? "primary" : "secondary"}
              size="sm"
              onClick={() => {
                setError(null);
                setMode("form");
              }}
            >
              Fill form
            </Button>
            <Button
              type="button"
              variant={mode === "import" ? "primary" : "secondary"}
              size="sm"
              leftIcon={<LinkIcon className="h-4 w-4" strokeWidth={1.5} />}
              onClick={() => {
                setError(null);
                setMode("import");
              }}
            >
              Import job link
            </Button>
          </div>

          <Field
            label={
              <span className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                Company
              </span>
            }
          >
            <Input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Acme India Pvt Ltd"
              autoFocus
            />
          </Field>

          {mode === "import" && (
            <Field
              label={
                <span className="flex items-center gap-2">
                  <LinkIcon className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                  Job link
                </span>
              }
            >
              <div className="flex items-center gap-2">
                <Input
                  value={importUrl}
                  onChange={(e) => setImportUrl(e.target.value)}
                  placeholder="Paste a job post link (LinkedIn, company careers, etc.)"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleImportFromUrl();
                  }}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={importing}
                  onClick={() => void handleImportFromUrl()}
                >
                  Import
                </Button>
              </div>
              <p className="text-micro text-ink-400 mt-1">
                We&apos;ll auto-fill the role title (and city if available). You can edit it below.
              </p>
            </Field>
          )}

          <Field
            label={
              <span className="flex items-center gap-2">
                <Briefcase className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                What are you hiring for?
              </span>
            }
          >
            <Input
              value={roleTitle}
              onChange={(e) => setRoleTitle(e.target.value)}
              placeholder="Senior Backend Engineer"
              onKeyDown={(e) => {
                if (e.key === "Enter") void finish();
              }}
            />
          </Field>

          <Field
            label={
              <span className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                City <span className="text-ink-400 font-normal">(optional)</span>
              </span>
            }
          >
            <Input
              value={roleCity}
              onChange={(e) => setRoleCity(e.target.value)}
              placeholder="Bangalore"
              onKeyDown={(e) => {
                if (e.key === "Enter") void finish();
              }}
            />
          </Field>

          {error && <p className="text-small text-destructive">{error}</p>}

          <Button
            variant="primary"
            className="w-full"
            loading={saving}
            onClick={() => void finish()}
            rightIcon={!saving ? <ArrowRight className="h-4 w-4" strokeWidth={1.5} /> : undefined}
          >
            Start hiring
          </Button>
          <p className="text-micro text-ink-400 text-center">
            JD, budget, and must-haves come next — in a chat with Nitya, not a form.
          </p>
        </div>
      </div>
    </div>
  );
}
