"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { User } from "@/components/brand/icons";
import { Button, useToast } from "@/components/ui";
import type { PublicProfile } from "@/lib/api/publicProfile";
import {
  listRoles,
  requestCandidateIntro,
  type RoleListItem,
} from "@/lib/api/recruiter";
import { recruiterAuthUrl } from "@/lib/auth/post-auth-redirect";

type PublicPortfolioRecruiterBarProps = {
  profile: PublicProfile;
};

export function PublicPortfolioRecruiterBar({ profile }: PublicPortfolioRecruiterBarProps) {
  const { toast } = useToast();
  const [roles, setRoles] = useState<RoleListItem[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState("");
  const [loadingRoles, setLoadingRoles] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const portfolioPath = `/p/${profile.slug}`;
  const candidateLabel = profile.display_name ?? "this candidate";

  useEffect(() => {
    if (!profile.viewer_is_recruiter) return;
    setLoadingRoles(true);
    void listRoles()
      .then((rows) => {
        setRoles(rows);
        const published = rows.filter((r) => r.published);
        if (published[0]) setSelectedRoleId(published[0].id);
        else if (rows[0]) setSelectedRoleId(rows[0].id);
      })
      .catch(() => undefined)
      .finally(() => setLoadingRoles(false));
  }, [profile.viewer_is_recruiter]);

  const publishedRoles = useMemo(() => roles.filter((r) => r.published), [roles]);

  async function handleRequestIntro() {
    if (!profile.candidate_id || !selectedRoleId || submitting) return;
    setSubmitting(true);
    try {
      const result = await requestCandidateIntro(
        selectedRoleId,
        profile.candidate_id,
        `I'd like to connect with ${candidateLabel} about a role on Hireschema.`,
      );
      if (result.error) {
        toast.error(result.error);
        return;
      }
      setSent(true);
      toast.success("Intro request sent — we'll notify the candidate.");
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't request intro");
    } finally {
      setSubmitting(false);
    }
  }

  if (!profile.viewer_is_recruiter) {
    if (profile.viewer_authenticated) return null;

    return (
      <div className="lg:col-span-2 rounded-xl border border-ink-100 bg-paper-1 px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <p className="text-small font-medium text-ink-900">Hiring for a role?</p>
          <p className="text-small text-ink-600 mt-0.5">
            Log in or sign up as a recruiter to view contact details and request a warm intro.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <Link
            href={recruiterAuthUrl({ from: portfolioPath, mode: "signin" })}
            className="inline-flex items-center justify-center rounded-lg border border-ink-200 bg-paper-0 px-4 py-2 text-small font-medium text-ink-900 hover:bg-ink-50"
          >
            Log in
          </Link>
          <Link
            href={recruiterAuthUrl({ from: portfolioPath })}
            className="inline-flex items-center justify-center rounded-lg bg-accent px-4 py-2 text-small font-semibold text-ink-900 hover:opacity-90"
          >
            Sign up as recruiter
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="lg:col-span-2 rounded-xl border border-accent/30 bg-accent/5 px-5 py-4 flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <User className="h-5 w-5 text-accent shrink-0 mt-0.5" strokeWidth={1.5} />
        <div className="min-w-0 space-y-1">
          <p className="text-small font-semibold text-ink-900">You&apos;re signed in as a recruiter</p>
          <p className="text-small text-ink-600">
            Review {candidateLabel}&apos;s profile below, then request a consent-first intro.
          </p>
        </div>
      </div>

      {loadingRoles ? (
        <p className="text-small text-ink-500">Loading your roles…</p>
      ) : roles.length === 0 ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-small text-ink-600">Create a role to request intros.</p>
          <Link
            href={`/recruiter/onboarding?from=${encodeURIComponent(portfolioPath)}`}
            className="text-small font-medium text-accent hover:underline"
          >
            Set up recruiter workspace →
          </Link>
        </div>
      ) : publishedRoles.length === 0 ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-small text-ink-600">
            Publish a role to the jobs feed before requesting intros.
          </p>
          <Link
            href={`/recruiter/roles/${roles[0]?.id}/intake`}
            className="text-small font-medium text-accent hover:underline"
          >
            Finish role setup →
          </Link>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <label className="flex-1 space-y-1.5">
            <span className="text-micro text-ink-500">Request intro for role</span>
            <select
              value={selectedRoleId}
              onChange={(e) => setSelectedRoleId(e.target.value)}
              className="w-full rounded-lg border border-ink-200 bg-paper-0 px-3 py-2 text-small text-ink-900"
            >
              {publishedRoles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.title}
                  {role.location_city ? ` · ${role.location_city}` : ""}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="primary"
            size="md"
            onClick={() => void handleRequestIntro()}
            loading={submitting}
            disabled={sent || !selectedRoleId}
            className="sm:shrink-0"
          >
            {sent ? "Intro requested" : "Request intro"}
          </Button>
        </div>
      )}
    </div>
  );
}
