"use client";

/**
 * Recruiter onboarding — company + hiring focus → inbox.
 * Distinct from candidate onboarding (Aarya CV wizard at /onboarding).
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, MapPin, User } from "@/components/brand/icons";
import { NityaFace } from "@/components/nitya/NityaFace";
import { Button, Card, CardBody, CardHeader } from "@/components/ui";
import { fetchMyProfile } from "@/lib/api/profile";
import {
  createRole,
  fetchRecruiterProfile,
  updateRecruiterProfile,
} from "@/lib/api/recruiter";

function Bubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-paper-1 rounded-lg rounded-tl-sm px-5 py-4 shadow-1 border border-accent/20 max-w-sm">
      {children}
    </div>
  );
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-paper-0 px-6 py-12 text-center">
      <NityaFace size="xl" />
      <div className="mt-8 max-w-sm">
        <Bubble>
          <p className="text-body text-ink-900 leading-relaxed">
            Hi — I&apos;m Nitya. Tell me about your company and what you&apos;re
            hiring for. I&apos;ll open your candidate inbox right away.
          </p>
        </Bubble>
      </div>
      <button
        type="button"
        onClick={onNext}
        className="mt-8 inline-flex items-center gap-2 rounded-full border border-accent/40 bg-paper-0 px-8 py-3 text-body text-ink-900 font-medium hover:bg-accent/5 transition-colors duration-fast"
      >
        Set up workspace <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </div>
  );
}

function ProfileStep({
  companyName,
  setCompanyName,
  title,
  setTitle,
  roleTitle,
  setRoleTitle,
  roleCity,
  setRoleCity,
  focus,
  setFocus,
  error,
  saving,
  onFinish,
}: {
  companyName: string;
  setCompanyName: (v: string) => void;
  title: string;
  setTitle: (v: string) => void;
  roleTitle: string;
  setRoleTitle: (v: string) => void;
  roleCity: string;
  setRoleCity: (v: string) => void;
  focus: string;
  setFocus: (v: string) => void;
  error: string | null;
  saving: boolean;
  onFinish: () => void;
}) {
  return (
    <div className="max-w-lg mx-auto px-6 py-10 space-y-6 min-h-screen">
      <div className="flex items-center gap-3">
        <NityaFace size="sm" />
        <div>
          <h1 className="text-h1 font-semibold text-ink-900">Recruiter workspace</h1>
          <p className="text-small text-ink-500 mt-0.5">
            Company details and your first role — you can refine everything later.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader title="Company & hiring" />
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
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-accent/20"
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
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-accent/20"
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
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-small font-medium text-ink-800">City</span>
            <input
              value={roleCity}
              onChange={(e) => setRoleCity(e.target.value)}
              placeholder="Bangalore"
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body focus:outline-none focus:ring-2 focus:ring-accent/20"
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
              className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body resize-none focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
          </label>
          {error && <p className="text-small text-destructive">{error}</p>}
          <Button
            variant="primary"
            className="w-full"
            loading={saving}
            onClick={onFinish}
          >
            Open inbox
          </Button>
          <p className="text-micro text-ink-400 text-center">
            Job seekers use a separate flow with Aarya — not this screen.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

export function RecruiterOnboardingFlow() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [companyName, setCompanyName] = useState("");
  const [title, setTitle] = useState("");
  const [roleTitle, setRoleTitle] = useState("");
  const [roleCity, setRoleCity] = useState("");
  const [focus, setFocus] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const roleCheckDone = useRef(false);

  useEffect(() => {
    if (roleCheckDone.current) return;
    roleCheckDone.current = true;
    void fetchMyProfile()
      .then((profile) => {
        if (profile.user?.role === "candidate") {
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
      <div className="min-h-screen flex items-center justify-center bg-paper-0 text-ink-500 text-small">
        Loading…
      </div>
    );
  }

  if (step === 0) {
    return <WelcomeStep onNext={() => setStep(1)} />;
  }

  return (
    <ProfileStep
      companyName={companyName}
      setCompanyName={setCompanyName}
      title={title}
      setTitle={setTitle}
      roleTitle={roleTitle}
      setRoleTitle={setRoleTitle}
      roleCity={roleCity}
      setRoleCity={setRoleCity}
      focus={focus}
      setFocus={setFocus}
      error={error}
      saving={saving}
      onFinish={() => void finish()}
    />
  );
}
