"use client";

/**
 * OnboardingFlow — post-LinkedIn wizard.
 *
 * This is the back half of a fixed signup pipeline. The first two stages run on
 * the server the moment LinkedIn OAuth completes (see /auth/callback →
 * POST /api/v1/auth/bootstrap):
 *
 *   1. Extract details from the LinkedIn OAuth login (metadata → linkedin_data)
 *   2. Run LinkDAPI profile enrichment (background) to pre-fill the dashboard
 *      from the candidate's LinkedIn URL. If OAuth didn't surface a vanity URL,
 *      the Resume step below offers a "confirm your LinkedIn URL" fallback so
 *      enrichment always has a URL to resolve.
 *
 * The wizard below continues that same fixed order on the client:
 *
 * Step 0  Welcome          Full-screen intro with Aarya avatar
 * Step 1  Goal             What kind of help are you looking for?
 * Step 1  Phone            Collect +91 mobile (saved for WhatsApp alerts)
 * Step 3  Legal / DPDP     ToS + marketing consent — the LAST form step
 * Step 4  Resume / CV      3. Scrape the candidate's CV (required path)
 * Step 5  Voice call       4. Talk to Aarya to round out the profile
 *
 * Legal/DPDP consent is intentionally the final input step: it sits right
 * before steps 4 → 5, which are the first stages that actually PROCESS personal
 * data (CV parse + voice call). Consent must precede processing under DPDP, so
 * it can't move any later than this.
 *
 * Steps 4 → 5 are SEQUENTIAL (CV first, then the call) — not an either/or — so
 * the candidate graph is built in the same order every time.
 *
 * Design: mirrors Jack & Jill AI aesthetic — conversational bubbles, hand-drawn
 * Aarya avatar, two-column layout on desktop (content left, illustration right).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Briefcase,
  Check,
  FileText,
  HelpCircle,
  Linkedin,
  Mic,
  Phone,
  Search,
  TrendingUp,
} from "lucide-react";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  updateMyProfile,
  type LocationScope,
  type RemotePreference,
} from "@/lib/api/profile";
import { ResumeUpload } from "@/components/resume/ResumeUpload";
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

const PROGRESS_STEPS = [
  { step: 1, label: "Phone" },
  { step: 2, label: "Goal" },
  { step: 3, label: "Consent" },
  { step: 4, label: "CV" },
  { step: 5, label: "Preferences" },
  { step: 6, label: "Call" },
] as const;

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

const ONBOARDING_STORAGE_KEY = "hireloop_onboarding_v1";

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

// ── Aarya avatar ──────────────────────────────────────────────────────────────

function AaryaFace({
  size = "md",
  withMic = false,
}: {
  size?: "xl" | "md" | "sm";
  withMic?: boolean;
}) {
  return (
    <div className="relative shrink-0 inline-flex">
      <div
        className={cn(
          "rounded-xl bg-ink-100 flex items-center justify-center text-ink-900",
          size === "xl" && "w-48 h-48",
          size === "md" && "w-14 h-14",
          size === "sm" && "w-10 h-10",
        )}
      >
        <svg
          viewBox="0 0 60 60"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={cn(
            size === "xl" && "w-28 h-28",
            size === "md" && "w-8 h-8",
            size === "sm" && "w-6 h-6",
          )}
        >
          {/* Eyebrows */}
          <path d="M11 19 Q16 14 21 17" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
          <path d="M39 17 Q44 14 49 19" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
          {/* Eyes */}
          <ellipse cx="19" cy="26" rx="3" ry="3.5" fill="currentColor"/>
          <ellipse cx="41" cy="26" rx="3" ry="3.5" fill="currentColor"/>
          {/* Nose — L-shape */}
          <path d="M30 28 L28 38 Q31 40 34 38" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          {/* Smile */}
          <path d="M17 46 Q30 56 43 46" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
        </svg>
      </div>

      {withMic && (
        <div className="absolute -bottom-1.5 -left-1.5 w-7 h-7 rounded-full bg-ink-900 flex items-center justify-center border-2 border-paper-0">
          <Mic className="h-3 w-3 text-paper-0" strokeWidth={2} />
        </div>
      )}
    </div>
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
            {greeting} I&apos;m Aarya. I&apos;m importing your LinkedIn profile
            in the background. One quick question, then your CV — and I&apos;ll
            line up India-only matches for you.
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
          CV parsing and voice calls only start after you accept. Raw voice audio
          is not stored — only the transcript (DPDP). Contact{" "}
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

// ── LinkedIn URL confirm (enrichment fallback) ────────────────────────────────
//
// LinkDAPI enrichment runs off the candidate's LinkedIn URL. LinkedIn OAuth
// doesn't always return a vanity URL, so we let the user confirm/correct it here
// (prefilled when we already have it). Saving (re)triggers enrichment so the
// dashboard is pre-filled. Sits after Legal consent → DPDP-safe.

const LINKEDIN_RE = /linkedin\.com\/in\/[^/?#\s]+/i;

type ProfileSnippet = {
  linkedin_url?: string | null;
  headline?: string | null;
  current_title?: string | null;
  current_company?: string | null;
  skills?: string[] | null;
  linkedin_data?: { linkdapi_enriched_at?: string } | null;
};

type LinkedInImportStatus = "idle" | "waiting" | "scraping" | "imported" | "timed_out";

function LinkedInConfirm() {
  const [url, setUrl] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [importStatus, setImportStatus] = useState<LinkedInImportStatus>("idle");
  const [preview, setPreview] = useState<ProfileSnippet | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    const res = await apiAuthFetch("/api/v1/me/profile");
    if (!res.ok) return null;
    const data = (await res.json()) as {
      candidate?: ProfileSnippet & { linkedin_data?: Record<string, unknown> };
    };
    const c = data.candidate;
    if (!c) return null;
    const liData = c.linkedin_data;
    const enrichedAt =
      liData && typeof liData === "object"
        ? (liData as { linkdapi_enriched_at?: string }).linkdapi_enriched_at
        : undefined;
    setPreview({
      headline: c.headline,
      current_title: c.current_title,
      current_company: c.current_company,
      skills: c.skills,
      linkedin_url: c.linkedin_url,
      linkedin_data: enrichedAt ? { linkdapi_enriched_at: enrichedAt } : null,
    });
    if (enrichedAt) setImportStatus("imported");
    else if (c.linkedin_url) setImportStatus("scraping");
    if (c.linkedin_url) {
      setUrl(c.linkedin_url);
      setSaved(true);
    }
    return c;
  }, []);

  useEffect(() => {
    let cancelled = false;
    void loadProfile()
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [loadProfile]);

  useEffect(() => {
    if (importStatus !== "scraping" && importStatus !== "waiting") return;
    let attempts = 0;
    const id = window.setInterval(() => {
      attempts += 1;
      void loadProfile().then((c) => {
        const enriched =
          c?.linkedin_data &&
          typeof c.linkedin_data === "object" &&
          "linkdapi_enriched_at" in (c.linkedin_data as object);
        if (enriched) {
          setImportStatus("imported");
          window.clearInterval(id);
        } else if (attempts >= 20) {
          setImportStatus("timed_out");
          window.clearInterval(id);
        }
      });
    }, 2500);
    return () => window.clearInterval(id);
  }, [importStatus, loadProfile]);

  const valid = LINKEDIN_RE.test(url.trim());

  async function save() {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    try {
      const res = await apiAuthFetch("/api/v1/me/linkedin", {
        method: "POST",
        body: JSON.stringify({ linkedin_url: url.trim() }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(data.detail ?? "Couldn't save that URL.");
        return;
      }
      const payload = (await res.json().catch(() => ({}))) as {
        enrichment_scheduled?: boolean;
      };
      setSaved(true);
      setImportStatus(payload.enrichment_scheduled ? "scraping" : "waiting");
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setSaving(false);
    }
  }

  const statusCopy: Record<LinkedInImportStatus, string> = {
    idle: "Add your LinkedIn URL — we scrape it after you accept consent.",
    waiting: "URL saved — scrape runs after DPDP consent on the previous step.",
    scraping: "Scraping your LinkedIn profile now…",
    imported: "LinkedIn profile imported",
    timed_out:
      "Scrape is taking longer than usual — your CV data still powers matches.",
  };

  return (
    <div className="mb-4 rounded-lg border border-ink-100 bg-paper-1 p-4 shadow-1">
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <Linkedin className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
        <h3 className="text-small font-semibold text-ink-900">
          LinkedIn profile import
        </h3>
        {importStatus !== "idle" && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-micro font-medium",
              importStatus === "imported" ? "text-accent" : "text-ink-500",
            )}
          >
            {importStatus === "imported" ? (
              <Check className="h-3 w-3" strokeWidth={2} />
            ) : importStatus === "scraping" ? (
              <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
            ) : null}
            {statusCopy[importStatus]}
          </span>
        )}
      </div>
      <p className="text-micro text-ink-500 mb-2.5 leading-relaxed">
        We read your public LinkedIn via LinkDAPI after consent — title, company,
        skills, and experience. You&apos;ll see imported fields below when done.
      </p>
      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setSaved(false);
          }}
          placeholder="https://www.linkedin.com/in/your-name"
          disabled={!loaded}
          className="flex-1 min-w-0 rounded-md border border-ink-100 bg-paper-1 px-3 py-2 text-small text-ink-900 placeholder:text-ink-300 outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => void save()}
          disabled={!valid || saving || saved}
          className={cn(
            "shrink-0 rounded-md px-4 py-2 text-small font-medium transition-colors duration-fast ease-out-soft",
            valid && !saving && !saved
              ? "bg-accent text-accent-fg hover:bg-accent-hover"
              : "bg-ink-50 text-ink-300 cursor-not-allowed",
          )}
        >
          {saved ? "Saved" : saving ? "Saving…" : "Save"}
        </button>
      </div>
      {error && <p className="mt-2 text-micro text-ink-700">{error}</p>}

      {importStatus === "imported" && preview && (
        <div className="mt-3 rounded-md border border-ink-100 bg-paper-0 p-3 text-micro text-ink-600 space-y-1">
          <p className="font-medium text-ink-800">Imported from LinkedIn</p>
          {preview.current_title && (
            <p>
              Role: <span className="text-ink-900">{preview.current_title}</span>
              {preview.current_company ? ` at ${preview.current_company}` : ""}
            </p>
          )}
          {preview.headline && (
            <p>
              Headline: <span className="text-ink-900">{preview.headline}</span>
            </p>
          )}
          {preview.skills && preview.skills.length > 0 && (
            <p>
              Skills:{" "}
              <span className="text-ink-900">
                {preview.skills.slice(0, 6).join(", ")}
                {preview.skills.length > 6 ? "…" : ""}
              </span>
            </p>
          )}
          {preview.linkedin_data?.linkdapi_enriched_at && (
            <p className="text-ink-400">
              Scraped at{" "}
              {new Date(preview.linkedin_data.linkdapi_enriched_at).toLocaleString(
                "en-IN",
                { dateStyle: "medium", timeStyle: "short" },
              )}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Step 4: Resume / CV scrape (sequential — comes before the call) ───────────

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
              Great, {firstName} — I&apos;ll help you {selectedGoal}. First, upload
              your CV so I can read your experience. Then we&apos;ll have a quick
              call to fill in the rest.
            </p>
          </Bubble>
        </div>

        <div className="ml-0 md:ml-[68px]">
          {/* LinkedIn URL fallback — ensures LinkDAPI enrichment always has a URL */}
          <LinkedInConfirm />

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
            href="/voice?from=onboarding"
            onClick={() => clearOnboardingProgress()}
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
  const [goal, setGoal] = useState("find_new_role");
  const [parsedResume, setParsedResume] = useState<ParsedResumeHint | undefined>();
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(ONBOARDING_STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as { step?: number; goal?: string };
        if (typeof saved.step === "number" && saved.step >= 0 && saved.step <= 6) {
          setStep(saved.step);
        }
        if (typeof saved.goal === "string") setGoal(saved.goal);
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
      sessionStorage.setItem(
        ONBOARDING_STORAGE_KEY,
        JSON.stringify({ step, goal }),
      );
    } catch {
      /* ignore */
    }
  }, [step, goal, hydrated]);

  const handleGoalNext = useCallback((g: string) => {
    if (g === "__back") {
      setStep(1);
      return;
    }
    setGoal(g);
    setStep(3);
  }, []);

  if (!hydrated) {
    return (
      <div className="min-h-screen bg-paper-0 flex items-center justify-center">
        <p className="text-small text-ink-500">Loading…</p>
      </div>
    );
  }

  // Each step fades up on entry (keyed by step so transitions re-animate) —
  // makes the flow feel like one continuous, guided motion.
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
        <PhoneStep
          onBack={() => setStep(0)}
          onNext={() => setStep(2)}
        />
      );

    case 2:
      return <GoalStep onNext={handleGoalNext} />;

    case 3:
      return (
        <LegalStep
          onBack={() => setStep(2)}
          onNext={() => setStep(4)}
        />
      );

    case 4:
      return (
        <ResumeStep
          onBack={() => setStep(3)}
          onNext={(parsed) => {
            setParsedResume(parsed);
            setStep(5);
          }}
          goal={goal}
          candidateName={candidateName}
        />
      );

    case 5:
      return (
        <JobPreferencesStep
          onBack={() => setStep(4)}
          onNext={() => setStep(6)}
          parsed={parsedResume}
          candidateName={candidateName}
        />
      );

    case 6:
      return (
        <VoiceCallStep
          onBack={() => setStep(5)}
          candidateName={candidateName}
        />
      );

    default:
      return null;
    }
  })();

  return <FadeUp key={step}>{content}</FadeUp>;
}
