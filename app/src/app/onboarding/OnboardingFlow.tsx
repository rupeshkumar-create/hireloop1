"use client";

/**
 * OnboardingFlow — post-LinkedIn wizard.
 *
 * This is the back half of a fixed signup pipeline. The first two stages run on
 * the server the moment LinkedIn OAuth completes (see /auth/callback →
 * POST /api/v1/auth/bootstrap):
 *
 *   1. Extract details from the LinkedIn OAuth login (metadata → linkedin_data +
 *      linkedin_url on the candidate row).
 *   2. After DPDP consent (Legal step), LinkDAPI enrichment runs in the
 *      background from that URL — no separate LinkedIn form in the wizard.
 *
 * Activation v2 — two client steps, then dashboard with jobs open:
 *
 * Step 0  Welcome          Full-screen intro with Aarya avatar
 * Step 1  Activate         CV upload + market + DPDP consent (single screen)
 *
 * Resume, CTC, and voice are dashboard boosters — not wizard gates.
 *
 * Design: mirrors Jack & Jill AI aesthetic — conversational bubbles, hand-drawn
 * Aarya avatar, two-column layout on desktop (content left, illustration right).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  Upload,
} from "@/components/brand/icons";
import { apiAuthFetch, ApiUnreachableError, probeApiHealth } from "@/lib/api/auth-fetch";
import { DIRECT_API_URL } from "@/lib/api/base-url";
import { fetchMyProfile } from "@/lib/api/profile";
import {
  uploadResumeAndApply,
  type ParsedResumeSummary,
} from "@/lib/api/onboardingProfile";
import { AaryaFace } from "@/components/aarya/AaryaFace";
import { markDashboardWelcomePending } from "@/lib/dashboard-welcome";
import { FadeUp } from "@/components/ui/motion";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { SUPPORTED_MARKETS, type MarketCode } from "@/lib/markets";
import type { SignupMethod } from "@/lib/auth/signup-method";
import { firstNameFromDisplayName } from "@/lib/auth/display-name";


const PROGRESS_STEPS = [{ step: 1, label: "Activate" }] as const;

const ONBOARDING_STORAGE_KEY = "hireloop_onboarding_v2";

async function formatOnboardingError(error: unknown): Promise<string> {
  if (error instanceof ApiUnreachableError) {
    const health = await probeApiHealth();
    if (health.ok) {
      return "Request failed after reaching the API. Please try again.";
    }
    const isLocal =
      typeof window !== "undefined" &&
      (window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1");
    if (isLocal) {
      return (
        "Can't reach the Hireloop API. Start the API on port 8000 " +
        `(NEXT_PUBLIC_API_URL is ${DIRECT_API_URL}), then try again.`
      );
    }
    return (
      "Can't reach the Hireloop API. On Vercel, set NEXT_PUBLIC_API_URL to your " +
      "Railway API URL, redeploy the app, and confirm Railway is running."
    );
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

function clearOnboardingProgress() {
  try {
    sessionStorage.removeItem(ONBOARDING_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function OnboardingProgress({ currentStep }: { currentStep: number }) {
  if (currentStep < 1) return null;

  const current = PROGRESS_STEPS.find((s) => s.step === currentStep);

  return (
    <nav
      aria-label="Onboarding progress"
      className="w-full max-w-md mx-auto mb-8 px-1"
    >
      {/* Announced to screen readers; the visual stepper below is decorative detail. */}
      <p className="sr-only">
        Step {currentStep} of {PROGRESS_STEPS.length}
        {current ? `: ${current.label}` : ""}
      </p>
      <div className="flex items-center justify-between gap-1">
        {PROGRESS_STEPS.map(({ step, label }, i) => {
          const done = currentStep > step;
          const active = currentStep === step;
          return (
            <div key={step} className="flex flex-1 items-center min-w-0">
              <div className="flex flex-col items-center gap-1 min-w-0 flex-1">
                <span
                  aria-current={active ? "step" : undefined}
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full text-micro font-semibold border transition-colors",
                    done && "bg-ink-900 border-ink-900 text-paper-0",
                    active && !done && "border-ink-900 text-ink-900 bg-paper-0",
                    !done && !active && "border-ink-200 text-ink-400 bg-paper-0",
                  )}
                >
                  {done ? <Check className="h-3 w-3" strokeWidth={2.5} /> : step}
                </span>
                <span
                  className={cn(
                    "text-micro truncate w-full text-center",
                    active || done ? "text-ink-700 font-medium" : "text-ink-400",
                  )}
                >
                  {label}
                </span>
              </div>
              {i < PROGRESS_STEPS.length - 1 && (
                <span
                  className={cn(
                    "h-px flex-1 mx-0.5 mb-4",
                    currentStep > step ? "bg-ink-900" : "bg-ink-200",
                  )}
                  aria-hidden
                />
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
}

// ── Chat bubble ───────────────────────────────────────────────────────────────

function Bubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-paper-1 rounded-lg rounded-tl-sm px-5 py-4 shadow-1 border border-ink-100 max-w-sm">
      {children}
    </div>
  );
}

// ── Step 0: Welcome ───────────────────────────────────────────────────────────

function WelcomeStep({
  onNext,
  candidateName,
  signupMethod,
}: {
  onNext: () => void;
  candidateName?: string;
  signupMethod: SignupMethod;
}) {
  const firstName = firstNameFromDisplayName(candidateName);
  const greeting = firstName ? `Hey ${firstName}!` : "Hey!";
  const introMessage =
    signupMethod === "linkedin"
      ? `${greeting} I'm Aarya. I'm pulling matches from your LinkedIn profile now. One quick screen — then your job matches are ready on the dashboard.`
      : `${greeting} I'm Aarya. On the next screen, upload your CV — I'll read your experience and line up job matches on your dashboard.`;

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-paper-0 px-6 py-12 text-center">
      <AaryaFace size="xl" />

      <div className="mt-8 max-w-sm">
        <Bubble>
          <p className="text-body text-ink-900 leading-relaxed">{introMessage}</p>
        </Bubble>
      </div>

      <button
        type="button"
        onClick={onNext}
        className="
          mt-8 inline-flex items-center gap-2 rounded-full
          border border-ink-200 bg-paper-0 px-8 py-3
          text-body text-ink-900 font-medium
          hover:bg-ink-50 hover:border-ink-400
          transition-colors duration-fast
        "
      >
        Get started <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </div>
  );
}

// ── Step 1: Activation (phone + goal + consent) ─────────────────────────────

function ActivationStep({
  onBack,
  candidateName,
  signupMethod,
}: {
  onBack: () => void;
  candidateName?: string;
  signupMethod: SignupMethod;
}) {
  const router = useRouter();
  const firstName = firstNameFromDisplayName(candidateName) ?? "there";

  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParsedResumeSummary | null>(null);
  const [market, setMarket] = useState<MarketCode>("IN");
  const [tosAccepted, setTosAccepted] = useState(false);
  const [marketingConsent, setMarketing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const hasResume = resumeFile !== null;

  // Phase 1: upload + parse the CV, then show "here's what I found" for review.
  async function handleUploadAndReview() {
    if (saving) return;
    if (!resumeFile) {
      setError(
        signupMethod === "linkedin"
          ? "Upload your CV — LinkedIn sign-in alone can't see your experience. (You can add your LinkedIn URL later from the dashboard.)"
          : "Upload your CV — I need your experience to find real matches. (You can add your LinkedIn URL later from the dashboard.)",
      );
      return;
    }
    if (!tosAccepted) {
      setError("Please accept the privacy policy and terms to continue.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const summary = await uploadResumeAndApply(resumeFile);
      const consentRes = await apiAuthFetch("/api/v1/me/onboarding-consent", {
        method: "POST",
        body: JSON.stringify({
          tos_accepted: true,
          marketing_emails: marketingConsent,
        }),
      });
      if (!consentRes.ok) {
        const data = (await consentRes.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? "Couldn't save consent.");
      }
      setParsed(summary);
    } catch (err) {
      setError(await formatOnboardingError(err));
    } finally {
      setSaving(false);
    }
  }

  // Phase 2: candidate confirmed the parse — record consent + finish onboarding.
  async function handleConfirm() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const completeRes = await apiAuthFetch("/api/v1/me/complete-onboarding", {
        method: "POST",
        body: JSON.stringify({
          skipped_voice: true,
          skipped_resume: resumeFile === null,
          market,
        }),
      });
      if (!completeRes.ok) {
        const data = (await completeRes.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? "Couldn't finish activation.");
      }

      clearOnboardingProgress();
      markDashboardWelcomePending();
      router.push("/dashboard");
    } catch (err) {
      setError(await formatOnboardingError(err));
    } finally {
      setSaving(false);
    }
  }

  const activationPrompt = parsed
    ? `Here's what I pulled from your CV, ${firstName} — does this look right? Confirm and I'll get the job search ready.`
    : signupMethod === "linkedin"
      ? `Almost there, ${firstName}! LinkedIn sign-in only shares your name and email — upload your CV so I can pull your experience and show real matches.`
      : `Almost there, ${firstName}! Upload your CV so I can pull your experience and show real matches.`;

  return (
    <div className="min-h-screen bg-paper-0 flex items-center px-6 py-12">
      <div className="max-w-lg mx-auto w-full">
        <OnboardingProgress currentStep={1} />

        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 mb-8 transition-colors"
        >
          ← Back
        </button>

        <div className="flex items-start gap-3 mb-6">
          <AaryaFace size="md" />
          <Bubble>
            <p className="text-body text-ink-900">{activationPrompt}</p>
          </Bubble>
        </div>

        {!parsed ? (
        <div className="space-y-5 rounded-lg border border-ink-100 bg-paper-1 p-5 shadow-1">
          <div className="space-y-2">
            <span className="text-small font-medium text-ink-700">Upload your CV</span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex w-full items-center gap-2 rounded-md border border-dashed border-ink-200 px-3 py-3 text-small text-ink-600 hover:border-ink-400 hover:bg-ink-50 transition-colors"
            >
              <Upload className="h-4 w-4 shrink-0 text-ink-500" strokeWidth={1.5} />
              <span className="truncate">
                {resumeFile ? resumeFile.name : "Choose a PDF or DOCX"}
              </span>
            </button>
            <p className="text-micro text-ink-400">
              Aarya reads your CV to build your profile and matches. You can add
              your LinkedIn URL later from the dashboard.
            </p>
          </div>

          <div className="space-y-2">
            <label htmlFor="onboarding-market" className="text-small font-medium text-ink-700">
              Your job market
            </label>
            <select
              id="onboarding-market"
              value={market}
              onChange={(e) => setMarket(e.target.value as MarketCode)}
              className="w-full rounded-md border border-ink-100 bg-paper-1 px-3 py-2.5 text-body text-ink-900"
            >
              {SUPPORTED_MARKETS.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.label}
                </option>
              ))}
            </select>
            <p className="text-micro text-ink-500">
              Matches and salaries are scoped to this region (India, US, or UK).
            </p>
          </div>

          <div className="space-y-3 pt-1 border-t border-ink-100">
            <label className="flex items-start gap-3 cursor-pointer group">
              <div className="relative mt-0.5 shrink-0">
                <input
                  type="checkbox"
                  checked={tosAccepted}
                  onChange={(e) => setTosAccepted(e.target.checked)}
                  className="sr-only"
                />
                <div
                  className={cn(
                    "w-5 h-5 rounded flex items-center justify-center border-2 transition-colors",
                    tosAccepted
                      ? "bg-accent border-accent"
                      : "border-ink-300 bg-paper-0 group-hover:border-ink-500",
                  )}
                >
                  {tosAccepted && (
                    <svg viewBox="0 0 12 10" fill="none" className="w-3 h-2.5">
                      <path d="M1 5l3 3 7-7" stroke="currentColor" className="text-on-accent" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>
              </div>
              <p className="text-small text-ink-700 leading-relaxed">
                I agree to the{" "}
                <Link href="/privacy" target="_blank" className="underline text-ink-900 hover:text-accent">
                  privacy policy
                </Link>
                {" "}and{" "}
                <Link href="/terms" target="_blank" className="underline text-ink-900 hover:text-accent">
                  terms of service
                </Link>
                .
              </p>
            </label>

            <label className="flex items-start gap-3 cursor-pointer group">
              <div className="relative mt-0.5 shrink-0">
                <input
                  type="checkbox"
                  checked={marketingConsent}
                  onChange={(e) => setMarketing(e.target.checked)}
                  className="sr-only"
                />
                <div
                  className={cn(
                    "w-5 h-5 rounded flex items-center justify-center border-2 transition-colors",
                    marketingConsent
                      ? "bg-accent border-accent"
                      : "border-ink-300 bg-paper-0 group-hover:border-ink-500",
                  )}
                >
                  {marketingConsent && (
                    <svg viewBox="0 0 12 10" fill="none" className="w-3 h-2.5">
                      <path d="M1 5l3 3 7-7" stroke="currentColor" className="text-on-accent" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>
              </div>
              <p className="text-small text-ink-700 leading-relaxed">
                Send me job alerts and updates (optional).
              </p>
            </label>
          </div>

          {error && (
            <p className="text-small text-destructive rounded-lg border border-destructive/30 bg-destructive-bg px-3 py-2">
              {error}
            </p>
          )}

          <Button
            variant="primary"
            size="lg"
            fullWidth
            loading={saving}
            disabled={!tosAccepted || !hasResume || saving}
            onClick={() => void handleUploadAndReview()}
            rightIcon={
              tosAccepted && hasResume && !saving ? (
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              ) : undefined
            }
          >
            {saving ? "Uploading your CV…" : "Review my CV"}
          </Button>
        </div>
        ) : (
        <div className="space-y-5 rounded-lg border border-ink-100 bg-paper-1 p-5 shadow-1">
          <div className="space-y-1">
            <p className="text-small font-medium text-ink-700">
              Here&apos;s what I read from your CV
            </p>
            <p className="text-micro text-ink-400">
              Looks off? Re-upload below — you can also refine details later in
              your profile.
            </p>
          </div>

          <div className="space-y-2 text-small text-ink-800">
            {parsed?.current_title && (
              <p>
                <span className="text-accent">✓</span>{" "}
                <span className="font-medium">{parsed.current_title}</span>
                {parsed.current_company ? ` · ${parsed.current_company}` : ""}
              </p>
            )}
            {typeof parsed?.years_experience === "number" &&
              parsed.years_experience > 0 && (
                <p>
                  <span className="text-accent">✓</span> {parsed.years_experience}{" "}
                  years of experience
                </p>
              )}
            {parsed?.skills && parsed.skills.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {parsed.skills.slice(0, 8).map((s) => (
                  <span
                    key={s}
                    className="text-micro px-2 py-0.5 rounded-sm bg-ink-100 text-ink-700"
                  >
                    {s}
                  </span>
                ))}
                {parsed.skills.length > 8 && (
                  <span className="text-micro text-ink-400 px-1 py-0.5">
                    +{parsed.skills.length - 8} more
                  </span>
                )}
              </div>
            )}
            {!parsed?.current_title &&
              !(parsed?.skills && parsed.skills.length > 0) && (
                <p className="text-ink-500">
                  I couldn&apos;t pull much from this file. Re-upload a clearer
                  CV, or continue and finish your profile from the dashboard.
                </p>
              )}
          </div>

          {error && (
            <p className="text-small text-destructive rounded-lg border border-destructive/30 bg-destructive-bg px-3 py-2">
              {error}
            </p>
          )}

          <Button
            variant="primary"
            size="lg"
            fullWidth
            loading={saving}
            onClick={() => void handleConfirm()}
            rightIcon={
              !saving ? (
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              ) : undefined
            }
          >
            {saving ? "Finishing…" : "Looks good — meet Aarya"}
          </Button>

          <button
            type="button"
            onClick={() => {
              setParsed(null);
              setResumeFile(null);
              setError(null);
            }}
            className="w-full text-micro text-ink-500 hover:text-ink-900 transition-colors"
          >
            Re-upload a different CV
          </button>
        </div>
        )}
      </div>
    </div>
  );
}


// ── Main flow ─────────────────────────────────────────────────────────────────

export function OnboardingFlow({
  candidateName: initialCandidateName,
  signupMethod = "email",
}: {
  candidateName?: string;
  signupMethod?: SignupMethod;
}) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [hydrated, setHydrated] = useState(false);
  const [candidateName, setCandidateName] = useState(initialCandidateName?.trim());
  const recruiterCheckDone = useRef(false);

  useEffect(() => {
    const next = initialCandidateName?.trim();
    if (next) setCandidateName(next);
  }, [initialCandidateName]);

  useEffect(() => {
    if (recruiterCheckDone.current) return;
    recruiterCheckDone.current = true;
    void fetchMyProfile()
      .then((profile) => {
        if (profile.user?.role === "recruiter") {
          router.replace("/recruiter/onboarding");
          return;
        }
        const name = profile.user?.full_name?.trim();
        if (name) setCandidateName(name);
      })
      .catch(() => {
        /* non-fatal — server page may still redirect */
      });
  }, [router]);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(ONBOARDING_STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as { step?: number };
        if (typeof saved.step === "number" && saved.step >= 0 && saved.step <= 1) {
          setStep(saved.step);
        }
      }
    } catch {
      /* ignore */
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify({ step }));
    } catch {
      /* ignore */
    }
  }, [step, hydrated]);

  if (!hydrated) {
    return (
      <div className="min-h-screen bg-paper-0 flex items-center justify-center">
        <p className="text-small text-ink-500">Loading…</p>
      </div>
    );
  }

  const content = (() => {
    switch (step) {
    case 0:
      return (
        <WelcomeStep
          onNext={() => setStep(1)}
          candidateName={candidateName}
          signupMethod={signupMethod}
        />
      );

    case 1:
      return (
        <ActivationStep
          onBack={() => setStep(0)}
          candidateName={candidateName}
          signupMethod={signupMethod}
        />
      );

    default:
      return null;
    }
  })();

  return <FadeUp key={step}>{content}</FadeUp>;
}
