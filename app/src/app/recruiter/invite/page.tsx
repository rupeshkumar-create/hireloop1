"use client";

/**
 * /recruiter/invite?token=… — a recruiter claims an intro invite.
 *
 * A candidate requested an intro for a job whose recruiter wasn't on Hireschema
 * yet, so we emailed a CTA. This page previews who's asking and lets the
 * (signed-in) recruiter accept — which activates the candidate's intro request
 * into their inbox.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Building2, CheckCircle, UserPlus } from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import {
  createRole,
  updateRecruiterProfile,
} from "@/lib/api/recruiter";
import { Button, Card, CardBody, EmptyState } from "@/components/ui";

type InvitePreview = {
  status: string;
  email: string | null;
  invited_name: string | null;
  expires_at: string | null;
  job_title: string | null;
  company_name: string | null;
  candidate_name: string | null;
  candidate_headline: string | null;
};

function InviteInner() {
  const router = useRouter();
  const token = useSearchParams().get("token");

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const load = useCallback(async () => {
    if (!token) {
      setError("This invite link is missing its token.");
      setLoading(false);
      return;
    }
    try {
      const data = await apiFetch<InvitePreview>(
        `/api/v1/recruiter/invite/${encodeURIComponent(token)}`
      );
      setPreview(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function accept() {
    if (!token) return;
    setAccepting(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/recruiter/invite/${encodeURIComponent(token)}/accept`, {
        method: "POST",
      });

      // Door A: minimal onboarding — company from invite, straight to inbox.
      if (preview) {
        try {
          await updateRecruiterProfile({
            company_name: preview.company_name ?? undefined,
            onboarding_complete: true,
          });
          if (preview.job_title) {
            await createRole({
              title: preview.job_title,
            });
          }
        } catch {
          /* non-fatal — user can finish profile later */
        }
      }

      setAccepted(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAccepting(false);
    }
  }

  const expired =
    preview?.expires_at != null && new Date(preview.expires_at) < new Date();
  const inactive =
    preview != null && ["accepted", "cancelled"].includes(preview.status);

  return (
    <div className="min-h-screen bg-paper-0 flex flex-col">
      <header className="flex h-14 shrink-0 items-center border-b border-ink-100 bg-paper-1 px-6">
        <Link href="/recruiter" className="text-h3 font-semibold text-ink-900">
          Hireschema <span className="text-ink-400 font-normal">for recruiters</span>
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center p-6">
      <div className="max-w-lg w-full">
        {loading && (
          <div className="h-40 rounded-lg bg-ink-100 animate-skeleton" />
        )}

        {!loading && error && !preview && (
          <EmptyState
            icon={<Building2 strokeWidth={1.5} />}
            title="Invite unavailable"
            description={error}
            action={
              <Link href="/recruiter">
                <Button variant="primary" size="sm">
                  Go to dashboard
                </Button>
              </Link>
            }
          />
        )}

        {!loading && preview && (
          <Card>
            <CardBody className="space-y-4">
              {accepted ? (
                <div className="text-center py-4 space-y-3">
                  <CheckCircle
                    className="h-10 w-10 text-accent mx-auto"
                    strokeWidth={1.5}
                  />
                  <div>
                    <p className="text-h3 font-semibold text-ink-900">
                      Invite accepted
                    </p>
                    <p className="text-small text-ink-500 mt-1">
                      {preview.candidate_name ?? "The candidate"}&apos;s intro
                      request is now in your inbox.
                    </p>
                  </div>
                  <Link href="/recruiter/inbox">
                    <Button variant="primary" size="sm">
                      Open inbox
                    </Button>
                  </Link>
                </div>
              ) : (
                <>
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-full bg-ink-100 flex items-center justify-center shrink-0">
                      <UserPlus className="h-5 w-5 text-ink-500" strokeWidth={1.5} />
                    </div>
                    <div>
                      <p className="text-body font-medium text-ink-900">
                        {preview.candidate_name ?? "A candidate"} wants an intro
                      </p>
                      {preview.candidate_headline && (
                        <p className="text-small text-ink-500">
                          {preview.candidate_headline}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg bg-ink-50 px-4 py-3 text-small text-ink-700">
                    For{" "}
                    <span className="font-medium text-ink-900">
                      {preview.job_title ?? "your role"}
                    </span>
                    {preview.company_name && <> at {preview.company_name}</>}.
                  </div>

                  {error && (
                    <p className="text-destructive text-small">{error}</p>
                  )}

                  {expired || inactive ? (
                    <p className="text-small text-ink-500">
                      This invite is no longer active.
                    </p>
                  ) : (
                    <Button
                      variant="primary"
                      onClick={() => void accept()}
                      loading={accepting}
                      className="w-full"
                    >
                      Accept & view candidate
                    </Button>
                  )}

                  <button
                    type="button"
                    onClick={() => router.push("/recruiter")}
                    className="w-full text-small text-ink-400 hover:text-ink-700 transition-colors"
                  >
                    Not now
                  </button>
                </>
              )}
            </CardBody>
          </Card>
        )}
      </div>
      </main>
    </div>
  );
}

export default function RecruiterInvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteInner />
    </Suspense>
  );
}
