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
 * Step 1  Activate         Phone + goal + DPDP consent (single screen)
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
  BookOpen,
  Briefcase,
  Check,
  FileText,
  HelpCircle,
  Mic,
  Phone,
  Search,
  TrendingUp,
  Upload,
} from "lucide-react";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  updateMyProfile,
  type LocationScope,
  type RemotePreference,
} from "@/lib/api/profile";
import {
  uploadResumeAndApply,
  type ParsedResumeSummary,
} from "@/lib/api/onboardingProfile";
import { ResumeUpload } from "@/components/resume/ResumeUpload";
import { AaryaFace } from "@/components/aarya/AaryaFace";
import { markDashboardWelcomePending } from "@/lib/dashboard-welcome";
import { FadeUp } from "@/components/ui/motion";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

// ── Goal options ─────────────────────────────────────────────────────────────

const GOALS = [
  {
    id: "find_new_role",
    label: "Find a new role",
    benefit: "Unlocks personalised job matches in INR / LPA",
    icon: Search,
  },
  {
    id: "discuss_job",
    label: "Discuss a job I saw",
    benefit: "Helps Aarya score that role against your profile",
    icon: Briefcase,
  },
  {
    id: "market_value",
    label: "Know my market value",
    benefit: "Better salary estimates for your city and level",
    icon: TrendingUp,
  },
  {
    id: "improve_resume",
    label: "Improve my resume",
    benefit: "Tailored fixes before you apply",
    icon: BookOpen,
  },
  {
    id: "career_coaching",
    label: "Career coaching",
    benefit: "Sharper next-step advice from Aarya",
    icon: Phone,
  },
  {
    id: "not_sure",
    label: "Not sure yet",
    benefit: "Aarya will suggest the best starting path",
    icon: HelpCircle,
  },
] as const;

const PROGRESS_STEPS = [{ step: 1, label: "Activate" }] as const;

type ParsedResumeHint = {
  current_title?: string;
  current_company?: string;
  years_experience?: number;
  skills?: string[];
  location_city?: string;
  location_state?: string;
};

function defaultSalaryLpa(years?: number): { min: number; max: number } {
  const y = years ?? 5;
  if (y <= 2) return { min: 6, max: 12 };
  if (y <= 5) return { min: 12, max: 20 };
  if (y <= 10) return { min: 18, max: 35 };
  return { min: 25, max: 50 };
}

const ONBOARDING_STORAGE_KEY = "hireloop_onboarding_v2";

function clearOnboardingProgress() {
  try {
    sessionStorage.removeItem(ONBOARDING_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function goalToLookingFor(goalId: string): string {
  return GOALS.find((g) => g.id === goalId)?.label ?? goalId;
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

// ── Illustration placeholders (right-side decorations) ────────────────────────

function CompassIllustration() {
  return (
    <div className="w-48 h-48 rounded-xl bg-ink-100 flex items-center justify-center">
      <svg viewBox="0 0 80 80" fill="none" className="w-24 h-24 text-ink-400">
        <circle cx="40" cy="40" r="36" stroke="currentColor" strokeWidth="2"/>
        <line x1="40" y1="10" x2="40" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        <line x1="40" y1="62" x2="40" y2="70" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        <line x1="10" y1="40" x2="18" y2="40" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        <line x1="62" y1="40" x2="70" y2="40" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        <path d="M40 16 L44 40 L40 36 L36 40 Z" fill="currentColor" opacity="0.8"/>
        <path d="M40 64 L36 40 L40 44 L44 40 Z" fill="currentColor" opacity="0.3"/>
      </svg>
    </div>
  );
}

// ── Step 0: Welcome ───────────────────────────────────────────────────────────

function WelcomeStep({
  onNext,
  candidateName,
}: {
  onNext: () => void;
  candidateName?: string;
}) {
  const firstName = candidateName?.split(" ")[0];
  const greeting = firstName ? `Hey ${firstName}!` : "Hey!";

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-paper-0 px-6 py-12 text-center">
      <AaryaFace size="xl" />

      <div className="mt-8 max-w-sm">
        <Bubble>
          <p className="text-body text-ink-900 leading-relaxed">
            {greeting} I&apos;m Aarya. I&apos;m pulling matches from your
            LinkedIn profile now. One quick screen — then your job matches are
            ready on the dashboard.
          </p>
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
}: {
  onBack: () => void;
  candidateName?: string;
}) {
  const router = useRouter();
  const firstName = candidateName?.split(" ")[0] ?? "there";

  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParsedResumeSummary | null>(null);
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
        "Upload your CV — LinkedIn sign-in alone can't see your experience. (You can add your LinkedIn URL later from the dashboard.)",
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
      setParsed(summary);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Couldn't read that file. Try another CV.",
      );
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

      const completeRes = await apiAuthFetch("/api/v1/me/complete-onboarding", {
        method: "POST",
        body: JSON.stringify({
          skipped_voice: true,
          skipped_resume: resumeFile === null,
        }),
      });
      if (!completeRes.ok) {
        const data = (await completeRes.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? "Couldn't finish activation.");
      }

      clearOnboardingProgress();
      markDashboardWelcomePending();
      router.push("/dashboard?panel=jobs");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

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
            <p className="text-body text-ink-900">
              {parsed
                ? `Here's what I pulled from your CV, ${firstName} — does this look right? Confirm and I'll start finding your matches.`
                : `Almost there, ${firstName}! LinkedIn sign-in only shares your name and email — upload your CV so I can pull your experience and show real matches.`}
            </p>
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
                      ? "bg-ink-900 border-ink-900"
                      : "border-ink-300 bg-paper-0 group-hover:border-ink-500",
                  )}
                >
                  {tosAccepted && (
                    <svg viewBox="0 0 12 10" fill="none" className="w-3 h-2.5">
                      <path d="M1 5l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
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
                      ? "bg-ink-900 border-ink-900"
                      : "border-ink-300 bg-paper-0 group-hover:border-ink-500",
                  )}
                >
                  {marketingConsent && (
                    <svg viewBox="0 0 12 10" fill="none" className="w-3 h-2.5">
                      <path d="M1 5l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>
              </div>
              <p className="text-small text-ink-700 leading-relaxed">
                Send me job alerts and updates (optional).
              </p>
            </label>
          </div>

          {error && <p className="text-small text-ink-700">{error}</p>}

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
            {saving ? "Reading your CV…" : "Review my CV"}
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

          {error && <p className="text-small text-ink-700">{error}</p>}

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
            {saving ? "Finishing…" : "Looks good — show my matches"}
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

// ── Legacy steps (resume / prefs / voice — kept for reference, unused in v2) ──

// ── Step 1: Goal ──────────────────────────────────────────────────────────────

function GoalStep({
  onNext,
}: {
  onNext: (goal: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedGoal = GOALS.find((g) => g.id === selected);

  async function handleNext() {
    if (!selected || saving) return;
    setSaving(true);
    setError(null);
    try {
      const res = await apiAuthFetch("/api/v1/me/profile", {
        method: "PATCH",
        body: JSON.stringify({ looking_for: goalToLookingFor(selected) }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(
          (data as { detail?: string }).detail ?? "Couldn't save your goal",
        );
      }
      onNext(selected);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your goal");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper-0 flex items-center px-6 py-12">
      <div className="max-w-3xl mx-auto w-full flex gap-16 items-start">

        {/* Left: content */}
        <div className="flex-1 min-w-0">
          <OnboardingProgress currentStep={2} />

          {/* Back button */}
          <button
            type="button"
            onClick={() => onNext("__back")}
            className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 mb-8 transition-colors"
          >
            ← Back
          </button>

          {/* Aarya + bubble */}
          <div className="flex items-start gap-3 mb-6">
            <AaryaFace size="md" />
            <Bubble>
              <p className="text-body text-ink-900">
                What would you like help with?
              </p>
            </Bubble>
          </div>

          {/* Option grid */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {GOALS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setSelected(id)}
                className={cn(
                  "flex items-center gap-2.5 rounded-xl border px-3 py-3 text-left text-small transition-all duration-fast",
                  selected === id
                    ? "border-ink-900 bg-ink-900 text-paper-0"
                    : "border-ink-200 bg-paper-1 text-ink-700 hover:border-ink-400 hover:bg-ink-50",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                <span className="leading-snug">{label}</span>
              </button>
            ))}
          </div>

          {selectedGoal && (
            <p className="mt-3 text-small text-ink-500">
              <span className="font-medium text-ink-700">Why this helps:</span>{" "}
              {selectedGoal.benefit}
            </p>
          )}

          {error && <p className="mt-3 text-small text-ink-700">{error}</p>}

          {/* Next */}
          <div className="mt-6">
            <button
              type="button"
              disabled={!selected || saving}
              onClick={() => void handleNext()}
              className={cn(
                "w-full rounded-xl py-3.5 text-body font-medium transition-colors duration-fast",
                selected && !saving
                  ? "bg-ink-900 text-paper-0 hover:bg-ink-800"
                  : "bg-ink-100 text-ink-400 cursor-not-allowed",
              )}
            >
              {saving ? "Saving…" : "Next"}
            </button>
          </div>
        </div>

        {/* Right: decoration */}
        <div className="hidden lg:flex items-center justify-center shrink-0 pt-16">
          <CompassIllustration />
        </div>
      </div>
    </div>
  );
}

// ── Step 2: Legal / DPDP ─────────────────────────────────────────────────────

function LegalStep({
  onNext,
  onBack,
}: {
  onNext: (marketingConsent: boolean) => void;
  onBack: () => void;
}) {
  const [tosAccepted, setTosAccepted]       = useState(false);
  const [marketingConsent, setMarketing]    = useState(false);
  const [saving, setSaving]                 = useState(false);

  const [error, setError] = useState<string | null>(null);

  async function handleNext() {
    if (!tosAccepted) return;
    setSaving(true);
    setError(null);
    try {
      const res = await apiAuthFetch("/api/v1/me/onboarding-consent", {
        method: "POST",
        body: JSON.stringify({
          tos_accepted: true,
          marketing_emails: marketingConsent,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(
          (data as { detail?: string }).detail ?? "Couldn't save consent",
        );
      }
      onNext(marketingConsent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save consent");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper-0 flex items-center px-6 py-12">
      <div className="max-w-md mx-auto w-full">
        <OnboardingProgress currentStep={3} />

        {/* Back */}
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 mb-8 transition-colors"
        >
          ← Back
        </button>

        {/* Aarya + bubble */}
        <div className="flex items-start gap-3 mb-8">
          <AaryaFace size="md" />
          <Bubble>
            <p className="text-body text-ink-900">
              The legal bit — it&apos;s important!
            </p>
          </Bubble>
        </div>

        {/* Checkboxes */}
        <div className="space-y-4">
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
                    ? "bg-ink-900 border-ink-900"
                    : "border-ink-300 bg-paper-0 group-hover:border-ink-500",
                )}
              >
                {tosAccepted && (
                  <svg viewBox="0 0 12 10" fill="none" className="w-3 h-2.5">
                    <path d="M1 5l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </div>
            </div>
            <p className="text-body text-ink-700 leading-relaxed">
              I agree to the{" "}
              <Link href="/privacy" target="_blank" className="underline text-ink-900 hover:text-accent">
                privacy policy
              </Link>
              {" "}and{" "}
              <Link href="/terms" target="_blank" className="underline text-ink-900 hover:text-accent">
                terms of service
              </Link>
              , and understand that AI can make mistakes.
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
                    ? "bg-ink-900 border-ink-900"
                    : "border-ink-300 bg-paper-0 group-hover:border-ink-500",
                )}
              >
                {marketingConsent && (
                  <svg viewBox="0 0 12 10" fill="none" className="w-3 h-2.5">
                    <path d="M1 5l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </div>
            </div>
            <p className="text-body text-ink-700 leading-relaxed">
              I&apos;d like to receive job alerts and updates from Hireloop.
            </p>
          </label>
        </div>

        <p className="mt-4 text-micro text-ink-500 leading-relaxed">
          Accepting lets us import your LinkedIn profile from your sign-in (we
          already have your profile URL). CV parsing and voice calls only start
          after you accept. Raw voice audio is not stored — only the transcript
          (DPDP). Contact{" "}
          <a href="mailto:privacy@hireloop.in" className="underline">
            privacy@hireloop.in
          </a>
          .
        </p>

        {error && <p className="mt-3 text-small text-ink-700">{error}</p>}

        {/* Next */}
        <button
          type="button"
          disabled={!tosAccepted || saving}
          onClick={() => void handleNext()}
          className={cn(
            "mt-6 w-full rounded-xl py-3.5 text-body font-medium transition-colors duration-fast",
            tosAccepted && !saving
              ? "bg-ink-900 text-paper-0 hover:bg-ink-800"
              : "bg-ink-100 text-ink-400 cursor-not-allowed",
          )}
        >
          {saving ? "Saving…" : "Next"}
        </button>
      </div>
    </div>
  );
}

// ── Step 2: Phone (+91, save only — WhatsApp alerts) ───────────────────────

function PhoneStep({
  onNext,
  onBack,
}: {
  onNext: () => void;
  onBack: () => void;
}) {
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const validPhone = /^[6-9]\d{9}$/.test(phone);
  const fullPhone = `+91${phone}`;

  async function handleSave() {
    if (!validPhone || saving) return;
    setSaving(true);
    setError(null);
    try {
      const res = await apiAuthFetch("/api/v1/auth/save-phone", {
        method: "POST",
        body: JSON.stringify({ phone: fullPhone }),
      });
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      if (!res.ok) {
        setError(data.detail ?? "Couldn't save your number. Please try again.");
        return;
      }
      setSaved(true);
    } catch {
      setError("Couldn't reach the server. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper-0 flex items-center px-6 py-12">
      <div className="max-w-md mx-auto w-full">
        <OnboardingProgress currentStep={1} />

        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 mb-8 transition-colors"
        >
          ← Back
        </button>

        <div className="flex items-start gap-3 mb-8">
          <AaryaFace size="md" />
          <Bubble>
            <p className="text-body text-ink-900">
              What&apos;s your +91 mobile? I&apos;ll use it on WhatsApp to ping you
              on strong job matches and intro updates.
            </p>
          </Bubble>
        </div>

        {!saved ? (
          <>
            <label className="block space-y-2">
              <span className="text-small font-medium text-ink-700">
                Mobile number
              </span>
              <div className="flex">
                <span className="inline-flex items-center gap-1.5 px-3 rounded-l-md border border-r-0 border-ink-100 bg-ink-50 text-ink-500 text-body">
                  <Phone className="h-4 w-4" strokeWidth={1.5} />
                  +91
                </span>
                <input
                  type="tel"
                  inputMode="numeric"
                  value={phone}
                  onChange={(e) =>
                    setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleSave();
                  }}
                  placeholder="98765 43210"
                  autoComplete="tel-national"
                  autoFocus
                  className="flex-1 min-w-0 rounded-r-md border border-ink-100 bg-paper-1 px-3 py-3 text-body text-ink-900 placeholder:text-ink-300 outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/15"
                />
              </div>
              <span className="text-micro text-ink-500">
                India only — must start with 6, 7, 8, or 9.
              </span>
            </label>

            <div
              className="mt-4 rounded-lg border border-ink-100 bg-ink-50/80 px-4 py-3"
              role="note"
            >
              <p className="text-small font-medium text-ink-900">
                WhatsApp on this number
              </p>
              <p className="mt-1 text-small text-ink-600 leading-relaxed">
                {validPhone ? (
                  <>
                    We&apos;ll send WhatsApp messages to{" "}
                    <span className="font-medium text-ink-900">{fullPhone}</span>{" "}
                    for job match alerts, intro status updates, and important
                    account notifications. No marketing spam — you can opt out in
                    Settings.
                  </>
                ) : (
                  <>
                    We&apos;ll send WhatsApp messages to this number for job match
                    alerts, intro updates, and account notifications. You can change
                    preferences anytime in Settings.
                  </>
                )}
              </p>
            </div>

            <Button
              variant="primary"
              size="lg"
              fullWidth
              loading={saving}
              disabled={!validPhone || saving}
              onClick={() => void handleSave()}
              rightIcon={
                validPhone && !saving ? (
                  <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
                ) : undefined
              }
              className="mt-6"
            >
              Save & continue
            </Button>
          </>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-4">
              <div className="flex items-center gap-2 text-ink-900">
                <Check className="h-5 w-5 text-accent shrink-0" strokeWidth={2} />
                <p className="text-body font-medium">Number saved</p>
              </div>
              <p className="mt-2 text-small text-ink-700 leading-relaxed">
                WhatsApp alerts will go to{" "}
                <span className="font-medium text-ink-900">{fullPhone}</span> when
                we find strong matches or your intro status changes.
              </p>
            </div>
            <Button
              variant="primary"
              size="lg"
              fullWidth
              onClick={onNext}
              rightIcon={<ArrowRight className="h-4 w-4" strokeWidth={1.5} />}
            >
              Continue
            </Button>
          </div>
        )}

        {error && <p className="mt-3 text-small text-destructive">{error}</p>}
      </div>
    </div>
  );
}

// ── Step 4: Resume / CV scrape (sequential — comes before preferences) ─────────

function ResumeStep({
  onBack,
  onNext,
  goal,
  candidateName,
}: {
  onBack: () => void;
  /** Advance to job preferences once the CV is parsed (or skipped). */
  onNext: (parsed?: ParsedResumeHint) => void;
  goal: string;
  candidateName?: string;
}) {
  const firstName = candidateName?.split(" ")[0] ?? "there";
  const selectedGoal =
    GOALS.find((g) => g.id === goal)?.label.toLowerCase() ?? "find the right role";

  return (
    <div className="min-h-screen bg-paper-0 flex items-center justify-center px-6 py-12">
      <div className="max-w-2xl mx-auto w-full">
        <OnboardingProgress currentStep={4} />

        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 mb-8 transition-colors"
        >
          ← Back
        </button>

        {/* Progress hint: CV first, then call */}
        <div className="ml-0 md:ml-[68px] mb-5 flex items-center gap-2 text-micro font-medium text-ink-500">
          <span className="inline-flex items-center gap-1.5 text-ink-900">
            <FileText className="h-3.5 w-3.5" strokeWidth={1.5} /> Step 1 · Upload CV
          </span>
          <span className="text-ink-300">→</span>
          <span className="inline-flex items-center gap-1.5">
            <Mic className="h-3.5 w-3.5" strokeWidth={1.5} /> Step 2 · Call with Aarya
          </span>
        </div>

        <div className="flex items-start gap-3 mb-6">
          <AaryaFace size="md" />
          <Bubble>
            <p className="text-body text-ink-900">
              Great, {firstName} — I&apos;m already pulling in your LinkedIn from
              sign-in. Upload your CV too so I can sharpen your matches for{" "}
              {selectedGoal}.
            </p>
          </Bubble>
        </div>

        <div className="ml-0 md:ml-[68px]">
          <div className="rounded-lg border border-ink-100 bg-paper-1 p-5 shadow-1">
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-ink-900 text-paper-0">
              <FileText className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <h2 className="text-h3 font-semibold text-ink-900">Upload your CV</h2>
            <p className="mt-1 text-small text-ink-500 leading-relaxed">
              Aarya parses your CV and fills your profile. Once it&apos;s in,
              we&apos;ll jump on a short call together.
            </p>
            <div className="mt-5">
              <ResumeUpload
                autoApply
                onDone={(_id, parsed) => onNext(parsed)}
              />
            </div>
          </div>

          <div className="mt-4 flex flex-col items-center gap-1.5">
            <button
              type="button"
              onClick={() => onNext()}
              className="text-small font-medium text-ink-500 underline underline-offset-4 transition-colors hover:text-ink-900"
            >
              I don&apos;t have my CV handy — talk to Aarya instead
            </button>
            <p className="text-micro text-ink-400 text-center">
              You can always add your CV later to improve match quality.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step 5: Job search preferences (defaults after CV parse) ─────────────────

function JobPreferencesStep({
  onBack,
  onNext,
  parsed,
  candidateName,
}: {
  onBack: () => void;
  onNext: () => void;
  parsed?: ParsedResumeHint;
  candidateName?: string;
}) {
  const salaryDefaults = defaultSalaryLpa(parsed?.years_experience);
  const [remotePreference, setRemotePreference] =
    useState<RemotePreference>("any");
  const [locationScope, setLocationScope] = useState<LocationScope>("city");
  const [locationCity, setLocationCity] = useState(parsed?.location_city ?? "");
  const [locationState, setLocationState] = useState(parsed?.location_state ?? "");
  const [ctcMinLpa, setCtcMinLpa] = useState(String(salaryDefaults.min));
  const [ctcMaxLpa, setCtcMaxLpa] = useState(String(salaryDefaults.max));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstName = candidateName?.split(" ")[0] ?? "there";

  async function handleSave() {
    setSaving(true);
    setError(null);
    const lpa = (v: string) => {
      const n = Number.parseFloat(v);
      return Number.isFinite(n) && n > 0 ? Math.round(n * 100_000) : undefined;
    };
    try {
      await updateMyProfile({
        remote_preference: remotePreference,
        location_scope: locationScope,
        location_city: locationCity.trim() || undefined,
        location_state: locationState.trim() || undefined,
        expected_ctc_min: lpa(ctcMinLpa),
        expected_ctc_max: lpa(ctcMaxLpa),
      });
      onNext();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save preferences.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper-0 flex items-center justify-center px-6 py-12">
      <div className="max-w-2xl mx-auto w-full">
        <OnboardingProgress currentStep={5} />

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
            <p className="text-body text-ink-900">
              Thanks {firstName} — I read your CV
              {parsed?.current_title ? ` (${parsed.current_title})` : ""}. These
              defaults power your job matches. Tweak them now or change anytime in
              chat.
            </p>
          </Bubble>
        </div>

        <div className="ml-0 md:ml-[68px] rounded-lg border border-ink-100 bg-paper-1 p-5 shadow-1 space-y-5">
          <div>
            <label className="text-small font-medium text-ink-900">
              How do you want to work?
            </label>
            <div className="mt-2 flex flex-wrap gap-2">
              {(
                [
                  ["any", "Open to anything"],
                  ["remote_only", "Remote only"],
                  ["onsite_only", "On-site only"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setRemotePreference(value)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-micro font-medium transition-colors",
                    remotePreference === value
                      ? "border-ink-900 bg-ink-900 text-paper-0"
                      : "border-ink-200 text-ink-600 hover:border-ink-400",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-small font-medium text-ink-900">
              How far should we search?
            </label>
            <div className="mt-2 flex flex-wrap gap-2">
              {(
                [
                  ["city", "My city only"],
                  ["state", "My state"],
                  ["country", "Anywhere in India"],
                  ["global", "Global"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setLocationScope(value)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-micro font-medium transition-colors",
                    locationScope === value
                      ? "border-ink-900 bg-ink-900 text-paper-0"
                      : "border-ink-200 text-ink-600 hover:border-ink-400",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-small font-medium text-ink-900">City</label>
              <input
                value={locationCity}
                onChange={(e) => setLocationCity(e.target.value)}
                placeholder="e.g. Bengaluru"
                className="mt-1 w-full rounded-md border border-ink-100 px-3 py-2 text-small"
              />
            </div>
            <div>
              <label className="text-small font-medium text-ink-900">State</label>
              <input
                value={locationState}
                onChange={(e) => setLocationState(e.target.value)}
                placeholder="e.g. Karnataka"
                className="mt-1 w-full rounded-md border border-ink-100 px-3 py-2 text-small"
              />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="text-small font-medium text-ink-900">
                Expected CTC (min LPA)
              </label>
              <input
                type="number"
                min={1}
                value={ctcMinLpa}
                onChange={(e) => setCtcMinLpa(e.target.value)}
                className="mt-1 w-full rounded-md border border-ink-100 px-3 py-2 text-small"
              />
            </div>
            <div>
              <label className="text-small font-medium text-ink-900">
                Expected CTC (max LPA)
              </label>
              <input
                type="number"
                min={1}
                value={ctcMaxLpa}
                onChange={(e) => setCtcMaxLpa(e.target.value)}
                className="mt-1 w-full rounded-md border border-ink-100 px-3 py-2 text-small"
              />
            </div>
          </div>

          {error && <p className="text-micro text-ink-700">{error}</p>}

          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="w-full"
          >
            {saving ? "Saving…" : "Save & continue"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Step 6: Voice call with Aarya (final step in the pipeline) ────────────────

function VoiceCallStep({
  onBack,
  candidateName,
}: {
  onBack: () => void;
  candidateName?: string;
}) {
  const router = useRouter();
  const [isSkipping, setIsSkipping] = useState(false);
  const [skipError, setSkipError] = useState<string | null>(null);
  const firstName = candidateName?.split(" ")[0] ?? "there";

  async function finishOnboarding(skippedVoice: boolean, skippedResume = false) {
    const res = await apiAuthFetch("/api/v1/me/complete-onboarding", {
      method: "POST",
      body: JSON.stringify({
        skipped_voice: skippedVoice,
        skipped_resume: skippedResume,
      }),
    });
    if (!res.ok) {
      const payload = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(payload?.detail ?? "Could not finish onboarding.");
    }
    clearOnboardingProgress();
    markDashboardWelcomePending();
    router.push("/dashboard?panel=jobs");
  }

  async function handleSkip() {
    setIsSkipping(true);
    setSkipError(null);
    try {
      await finishOnboarding(true, true);
    } catch (err) {
      setSkipError(err instanceof Error ? err.message : "Could not finish onboarding.");
    } finally {
      setIsSkipping(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper-0 flex items-center justify-center px-6 py-12">
      <div className="max-w-2xl mx-auto w-full">
        <OnboardingProgress currentStep={6} />

        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 mb-8 transition-colors"
        >
          ← Back
        </button>

        {/* Progress hint: CV + prefs done, call now */}
        <div className="ml-0 md:ml-[68px] mb-5 flex items-center gap-2 text-micro font-medium text-ink-500">
          <span className="inline-flex items-center gap-1.5 text-ink-400 line-through">
            <FileText className="h-3.5 w-3.5" strokeWidth={1.5} /> Step 1 · Upload CV
          </span>
          <span className="text-ink-300">→</span>
          <span className="inline-flex items-center gap-1.5 text-ink-900">
            <Mic className="h-3.5 w-3.5" strokeWidth={1.5} /> Step 2 · Call with Aarya
          </span>
        </div>

        <div className="flex items-start gap-3 mb-6">
          <AaryaFace size="md" withMic />
          <Bubble>
            <p className="text-body text-ink-900">
              Almost there, {firstName}! Let&apos;s have a quick 15-min call so I
              can understand your goals and preferences, then I&apos;ll line up
              your matches.
            </p>
          </Bubble>
        </div>

        <div className="ml-0 md:ml-[68px]">
          <Link
            href="/dashboard?voice=deep&panel=jobs"
            onClick={() => {
              clearOnboardingProgress();
              markDashboardWelcomePending();
            }}
            className="group flex flex-col rounded-lg border border-ink-100 bg-paper-1 p-5 shadow-1 transition-shadow duration-fast ease-out-soft hover:shadow-2"
          >
            <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-ink-900 text-paper-0">
              <Mic className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <h2 className="text-h3 font-semibold text-ink-900">
              15-min call with Aarya
            </h2>
            <p className="mt-1 text-small text-ink-500 leading-relaxed">
              Talk through your goals, experience, and preferences with the
              candidate agent. This sharpens your matches the most.
            </p>
            <span className="mt-auto inline-flex items-center gap-2 pt-6 text-small font-medium text-ink-900">
              Start voice call
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" strokeWidth={1.5} />
            </span>
          </Link>

          <div className="mt-4 flex flex-col items-center gap-2">
            <button
              type="button"
              onClick={() => void handleSkip()}
              disabled={isSkipping}
              className="text-small font-medium text-ink-500 underline underline-offset-4 transition-colors hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSkipping ? "Finishing..." : "Skip the call — take me to my matches"}
            </button>
            {skipError && (
              <p className="text-micro text-ink-700 text-center">
                {skipError}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main flow ─────────────────────────────────────────────────────────────────

export function OnboardingFlow({ candidateName }: { candidateName?: string }) {
  const [step, setStep] = useState(0);
  const [hydrated, setHydrated] = useState(false);

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
        />
      );

    case 1:
      return (
        <ActivationStep
          onBack={() => setStep(0)}
          candidateName={candidateName}
        />
      );

    default:
      return null;
    }
  })();

  return <FadeUp key={step}>{content}</FadeUp>;
}
