"use client";

/**
 * Recruiter onboarding — Door B (cold signup).
 *
 * Company + optional role title/city → inbox. No forced full JD wizard.
 * Door A (invite) skips this via /recruiter/invite after accept.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, MapPin, User } from "@/components/brand/icons";
import { Button, Card, CardBody, CardHeader } from "@/components/ui";
import {
  createRole,
  fetchRecruiterProfile,
  updateRecruiterProfile,
} from "@/lib/api/recruiter";

export default function RecruiterOnboardingPage() {
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [title, setTitle] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [roleCity, setRoleCity] = useState("");
  const [focus, setFocus] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRecruiterProfile()
      .then((p) => {
        if (p.onboarding_complete) {
          router.replace("/recruiter/inbox");
          return;
        }
        setCompanyName(p.company_name === "My Company" ? "" : p.company_name ?? "");
        setTitle(p.title ?? "");
        setFocus(p.hiring_focus ?? "");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [router]);

  async function finish() {
    if (!companyName.trim()) {
      setError("Company name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateRecruiterProfile({
        company_name: companyName.trim(),
        recruiter_title: title.trim() || undefined,
        hiring_focus: focus.trim() || undefined,
        onboarding_complete: true,
      });

      const hiringTitle = roleTitle.trim() || focus.trim().split(/[\n,]/)[0]?.trim();
      if (hiringTitle) {
        await createRole({
          title: hiringTitle.slice(0, 120),
          location_city: roleCity.trim() || undefined,
          jd_text: focus.trim() || undefined,
        });
      }

      router.push("/recruiter/inbox");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-lg mx-auto px-6 py-16 text-center text-ink-500 text-small">
        Loading…
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto px-6 py-10 space-y-6">
      <div>
        <h1 className="text-h1 font-semibold text-ink-900">Welcome to Hireloop</h1>
        <p className="text-small text-ink-500 mt-1">
          Tell Nitya about your company and what you&apos;re hiring for — then
          your candidate inbox opens right away.
        </p>
      </div>

      <Card>
        <CardHeader title="Recruiter profile" />
        <CardBody className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-small font-medium text-ink-800 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
              Company name
            </span>
            <input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Acme India Pvt Ltd"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-small font-medium text-ink-800 flex items-center gap-2">
              <User className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
              Your title
            </span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Head of Talent"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-small font-medium text-ink-800 flex items-center gap-2">
              <MapPin className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
              Role you&apos;re hiring for (optional)
            </span>
            <input
              value={roleTitle}
              onChange={(e) => setRoleTitle(e.target.value)}
              placeholder="Senior Backend Engineer"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-small font-medium text-ink-800">City</span>
            <input
              value={roleCity}
              onChange={(e) => setRoleCity(e.target.value)}
              placeholder="Bangalore"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-small font-medium text-ink-800">
              Hiring focus (optional)
            </span>
            <textarea
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              rows={3}
              placeholder="e.g. Senior backend engineers in Bangalore, fintech"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body resize-none focus:outline-none focus:ring-2 focus:ring-ink-900/10"
            />
          </label>
          {error && <p className="text-small text-destructive">{error}</p>}
          <Button
            variant="primary"
            className="w-full"
            loading={saving}
            onClick={() => void finish()}
          >
            Open inbox
          </Button>
          <p className="text-micro text-ink-400 text-center">
            You can refine the full role brief anytime from Roles.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
