"use client";

/**
 * In-chat profile completion flow.
 *
 * Rendered inside the chat thread when the candidate taps the "Profile X%
 * complete" chip. Two paths:
 *   1. Talk to Aarya  → routes to the voice call (Aarya runs it like a recruiter
 *      and pulls the missing details conversationally).
 *   2. Fill it in     → a gamified, one-question-per-step form covering every
 *      user-fillable profile field. Completeness climbs as they answer.
 *
 * On finish it PATCHes /me/profile and tells the parent to refresh so the chip
 * and matches update.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  PencilLine,
  Phone,
  Sparkles,
  X,
} from "lucide-react";

import { Button, Card, CardBody, Input, Select, Textarea } from "@/components/ui";
import {
  fetchMyProfile,
  updateMyProfile,
  type LocationScope,
  type MyProfileData,
  type ProfilePatch,
  type RemotePreference,
} from "@/lib/api/profile";
import { cn } from "@/lib/utils";

type StepType = "text" | "textarea" | "number" | "select";

type Step = {
  id: string;
  prompt: string;
  hint?: string;
  type: StepType;
  placeholder?: string;
  suffix?: string;
  options?: { label: string; value: string }[];
};

// "Everything possible" — every field a human can actually answer (the rest of
// the career-intelligence points are inferred from these + the résumé).
const STEPS: Step[] = [
  { id: "current_title", prompt: "What's your current role?", hint: "Your job title today.", type: "text", placeholder: "e.g. Product Designer" },
  { id: "current_company", prompt: "Where are you working now?", type: "text", placeholder: "e.g. LimeDock" },
  {
    id: "years_experience",
    prompt: "How many years of experience do you have?",
    type: "select",
    options: [
      { label: "Fresher (0–1 yrs)", value: "1" },
      { label: "2–3 years", value: "3" },
      { label: "4–6 years", value: "5" },
      { label: "7–10 years", value: "8" },
      { label: "10+ years", value: "12" },
    ],
  },
  { id: "skills", prompt: "What are your top skills?", hint: "Comma-separated — the more specific, the better the matches.", type: "text", placeholder: "Figma, UX research, growth, Python" },
  { id: "expected_ctc_min", prompt: "Minimum CTC you'd accept?", hint: "In LPA (lakhs per annum).", type: "number", placeholder: "10", suffix: "LPA" },
  { id: "expected_ctc_max", prompt: "And the top of your range?", hint: "In LPA — leave blank if open.", type: "number", placeholder: "18", suffix: "LPA" },
  { id: "current_ctc", prompt: "What's your current CTC?", hint: "In LPA — stays private, used only to gauge fit.", type: "number", placeholder: "12", suffix: "LPA" },
  {
    id: "notice_period_days",
    prompt: "What's your notice period?",
    type: "select",
    options: [
      { label: "Immediate", value: "0" },
      { label: "15 days", value: "15" },
      { label: "30 days", value: "30" },
      { label: "60 days", value: "60" },
      { label: "90 days", value: "90" },
    ],
  },
  { id: "location_city", prompt: "Which city are you based in?", type: "text", placeholder: "e.g. Bengaluru" },
  { id: "location_state", prompt: "And the state?", type: "text", placeholder: "e.g. Karnataka" },
  {
    id: "remote_preference",
    prompt: "How do you want to work?",
    type: "select",
    options: [
      { label: "Open to anything", value: "any" },
      { label: "Remote only", value: "remote_only" },
      { label: "On-site only", value: "onsite_only" },
    ],
  },
  {
    id: "location_scope",
    prompt: "How far are you willing to look for roles?",
    hint: "We rank jobs by this — wider scope surfaces more openings.",
    type: "select",
    options: [
      { label: "My city only", value: "city" },
      { label: "Anywhere in my state", value: "state" },
      { label: "Anywhere in India", value: "country" },
      { label: "Global (open to anywhere)", value: "global" },
    ],
  },
  { id: "looking_for", prompt: "What roles are you aiming for next?", hint: "Your target titles or the kind of work you want.", type: "textarea", placeholder: "e.g. Senior Product Designer, Growth Manager at an early-stage SaaS" },
];

/** Mirrors backend `_completeness` weights in career_intelligence/engine.py */
const FIELD_WEIGHTS: Record<string, number> = {
  current_title: 12,
  current_company: 10,
  years_experience: 8,
  skills: 12,
  expected_ctc_min: 14,
  expected_ctc_max: 0,
  current_ctc: 10,
  notice_period_days: 8,
  location_city: 8,
  remote_preference: 6,
  looking_for: 10,
};

function buildPatch(answers: Record<string, string>): ProfilePatch {
  const patch: ProfilePatch = {};
  const lpaToInr = (v: string): number | undefined => {
    const n = Number.parseFloat(v);
    return Number.isFinite(n) && n > 0 ? Math.round(n * 100_000) : undefined;
  };
  const str = (v: string | undefined) => (v && v.trim() ? v.trim() : undefined);
  const int = (v: string | undefined) => {
    if (!v) return undefined;
    const n = Number.parseInt(v, 10);
    return Number.isFinite(n) ? n : undefined;
  };

  if (str(answers.current_title)) patch.current_title = answers.current_title.trim();
  if (str(answers.current_company)) patch.current_company = answers.current_company.trim();
  if (int(answers.years_experience) != null) patch.years_experience = int(answers.years_experience);
  if (str(answers.skills)) {
    const skills = answers.skills
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (skills.length) patch.skills = skills;
  }
  if (lpaToInr(answers.expected_ctc_min ?? "") != null) patch.expected_ctc_min = lpaToInr(answers.expected_ctc_min);
  if (lpaToInr(answers.expected_ctc_max ?? "") != null) patch.expected_ctc_max = lpaToInr(answers.expected_ctc_max);
  if (lpaToInr(answers.current_ctc ?? "") != null) patch.current_ctc = lpaToInr(answers.current_ctc);
  if (int(answers.notice_period_days) != null) patch.notice_period_days = int(answers.notice_period_days);
  if (str(answers.location_city)) patch.location_city = answers.location_city.trim();
  if (str(answers.location_state)) patch.location_state = answers.location_state.trim();
  if (answers.remote_preference) patch.remote_preference = answers.remote_preference as RemotePreference;
  if (answers.location_scope) patch.location_scope = answers.location_scope as LocationScope;
  if (str(answers.looking_for)) patch.looking_for = answers.looking_for.trim();

  return patch;
}

type Props = {
  profile: MyProfileData | null;
  completeness: number | null;
  onClose: () => void;
  onSaved: () => void;
};

export function ProfileCompletionFlow({ profile, completeness, onClose, onSaved }: Props) {
  const [phase, setPhase] = useState<"choose" | "form" | "done">("choose");
  const [stepIndex, setStepIndex] = useState(0);
  const [prefilled, setPrefilled] = useState<Record<string, string>>(() => prefill(profile));
  const [answers, setAnswers] = useState<Record<string, string>>(() => prefill(profile));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pull the freshest profile so we never ask for what LinkedIn/résumé already
  // gave us. Merge non-destructively (never clobber something the user just typed).
  useEffect(() => {
    let cancelled = false;
    fetchMyProfile()
      .then((fresh) => {
        if (cancelled) return;
        const pf = prefill(fresh);
        setPrefilled(pf);
        setAnswers((prev) => {
          const next = { ...prev };
          for (const [k, v] of Object.entries(pf)) {
            if (v && !(next[k] ?? "").trim()) next[k] = v;
          }
          return next;
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // Only ask for the fields we DON'T already have — known fields are skipped.
  const pendingSteps = useMemo(
    () => STEPS.filter((s) => !(prefilled[s.id] ?? "").trim()),
    [prefilled]
  );

  const base = completeness ?? 8;
  const projected = useMemo(() => {
    let newlyAdded = 0;
    for (const step of STEPS) {
      const weight = FIELD_WEIGHTS[step.id] ?? 0;
      if (!weight) continue;
      const answered = (answers[step.id] ?? "").trim();
      const alreadyHad = (prefilled[step.id] ?? "").trim();
      if (answered && !alreadyHad) newlyAdded += weight;
    }
    return Math.min(100, Math.round(base + newlyAdded));
  }, [base, answers, prefilled]);

  const total = pendingSteps.length;
  const step = pendingSteps[Math.min(stepIndex, Math.max(0, total - 1))];
  const isLast = stepIndex >= total - 1;

  const setAnswer = (value: string) =>
    step && setAnswers((prev) => ({ ...prev, [step.id]: value }));

  const goNext = async () => {
    if (!isLast) {
      setStepIndex((i) => i + 1);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const patch = buildPatch(answers);
      if (Object.keys(patch).length > 0) {
        await updateMyProfile(patch);
      }
      onSaved();
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save — try again.");
    } finally {
      setSaving(false);
    }
  };

  // ── Chooser ────────────────────────────────────────────────────────────────
  if (phase === "choose") {
    return (
      <Shell onClose={onClose}>
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" strokeWidth={2} />
          <p className="text-small font-semibold text-ink-900">
            Let&apos;s finish your profile
          </p>
        </div>
        <p className="mt-1 text-small text-ink-600">
          You&apos;re at {base}%. Completing it sharpens your matches and how
          recruiters rank you. Two ways to do it:
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Link
            href="/voice"
            className="group rounded-xl border border-ink-200 bg-paper-1 p-3 text-left transition-colors hover:border-ink-300 hover:bg-ink-50"
          >
            <Phone className="h-5 w-5 text-ink-900" strokeWidth={1.5} />
            <p className="mt-2 text-small font-semibold text-ink-900">
              Talk it through with Aarya
            </p>
            <p className="mt-0.5 text-micro text-ink-500">
              A quick call — she asks, you answer, she fills it in.
            </p>
          </Link>
          <button
            type="button"
            onClick={() => setPhase("form")}
            className="group rounded-xl border border-ink-200 bg-paper-1 p-3 text-left transition-colors hover:border-ink-300 hover:bg-ink-50"
          >
            <PencilLine className="h-5 w-5 text-ink-900" strokeWidth={1.5} />
            <p className="mt-2 text-small font-semibold text-ink-900">
              Fill it in yourself
            </p>
            <p className="mt-0.5 text-micro text-ink-500">
              {STEPS.length} quick questions, one at a time. ~2 minutes.
            </p>
          </button>
        </div>
      </Shell>
    );
  }

  // ── Done ─────────────────────────────────────────────────────────────────────
  if (phase === "done") {
    return (
      <Shell onClose={onClose}>
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-paper-0">
            <Check className="h-4 w-4" strokeWidth={2.5} />
          </span>
          <p className="text-small font-semibold text-ink-900">
            Nice — profile updated to ~{projected}%
          </p>
        </div>
        <p className="mt-1 text-small text-ink-600">
          I&apos;ll re-rank your matches with the new details. Ask me to
          &ldquo;find my best matches&rdquo; whenever you&apos;re ready.
        </p>
        <div className="mt-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </Shell>
    );
  }

  // ── Form ─────────────────────────────────────────────────────────────────────
  // Nothing left to ask — everything we'd collect is already on the profile.
  if (!step) {
    return (
      <Shell onClose={onClose}>
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-paper-0">
            <Check className="h-4 w-4" strokeWidth={2.5} />
          </span>
          <p className="text-small font-semibold text-ink-900">
            Your profile already has the essentials
          </p>
        </div>
        <p className="mt-1 text-small text-ink-600">
          I&apos;ve got your role, skills, and preferences from LinkedIn and your résumé.
          Ask me to &ldquo;find my best matches&rdquo; whenever you&apos;re ready.
        </p>
        <div className="mt-3">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell onClose={onClose}>
      {/* Progress + projected completeness (pr-6 clears the close button) */}
      <div className="mb-3 pr-6">
        <div className="mb-1 flex items-center justify-between text-micro text-ink-500">
          <span>
            Question {stepIndex + 1} of {total}
          </span>
          <span className="font-semibold text-accent">{projected}% complete</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
          <div
            className="h-full rounded-full bg-accent transition-all duration-300"
            style={{ width: `${Math.max(6, ((stepIndex + 1) / total) * 100)}%` }}
          />
        </div>
      </div>

      <p className="text-body font-semibold text-ink-900">{step.prompt}</p>
      {step.hint && <p className="mt-0.5 text-micro text-ink-500">{step.hint}</p>}

      <div className="mt-3">
        {step.type === "select" ? (
          <Select
            autoFocus
            value={answers[step.id] ?? ""}
            onChange={(e) => setAnswer(e.target.value)}
            options={[{ label: "Select…", value: "" }, ...(step.options ?? [])]}
          />
        ) : step.type === "textarea" ? (
          <Textarea
            autoFocus
            value={answers[step.id] ?? ""}
            placeholder={step.placeholder}
            onChange={(e) => setAnswer(e.target.value)}
          />
        ) : (
          <Input
            autoFocus
            type={step.type === "number" ? "number" : "text"}
            inputMode={step.type === "number" ? "decimal" : undefined}
            value={answers[step.id] ?? ""}
            placeholder={step.placeholder}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !saving) {
                e.preventDefault();
                void goNext();
              }
            }}
            rightIcon={step.suffix ? <span className="text-micro">{step.suffix}</span> : undefined}
          />
        )}
      </div>

      {error && <p className="mt-2 text-micro text-destructive">{error}</p>}

      <div className="mt-4 flex items-center justify-between">
        <button
          type="button"
          disabled={stepIndex === 0 || saving}
          onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
          className={cn(
            "inline-flex items-center gap-1 text-micro text-ink-500 hover:text-ink-900",
            (stepIndex === 0 || saving) && "invisible"
          )}
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>

        <div className="flex items-center gap-2">
          {!isLast && (
            <button
              type="button"
              onClick={() => setStepIndex((i) => i + 1)}
              disabled={saving}
              className="text-micro text-ink-500 underline underline-offset-2 hover:text-ink-900"
            >
              Skip
            </button>
          )}
          <Button size="sm" onClick={() => void goNext()} loading={saving}>
            {isLast ? "Finish" : "Next"}
            {!isLast && <ArrowRight className="ml-1 h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>
    </Shell>
  );
}

function Shell({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <Card className="relative mx-auto w-full max-w-md border-accent/30">
      <CardBody>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-2 top-2 rounded-full p-1 text-ink-400 hover:bg-ink-50 hover:text-ink-900"
        >
          <X className="h-4 w-4" />
        </button>
        {children}
      </CardBody>
    </Card>
  );
}

function prefill(profile: MyProfileData | null): Record<string, string> {
  const c = profile?.candidate;
  if (!c) return {};
  const out: Record<string, string> = {};
  const inrToLpa = (v: number | null | undefined) =>
    v != null && v > 0 ? String(Math.round(v / 100_000)) : "";
  if (c.current_title) out.current_title = c.current_title;
  if (c.current_company) out.current_company = c.current_company;
  if (c.years_experience != null) out.years_experience = String(c.years_experience);
  if (c.skills?.length) out.skills = c.skills.join(", ");
  out.expected_ctc_min = inrToLpa(c.expected_ctc_min);
  out.expected_ctc_max = inrToLpa(c.expected_ctc_max);
  out.current_ctc = inrToLpa(c.current_ctc);
  if (c.notice_period_days != null) out.notice_period_days = String(c.notice_period_days);
  if (c.location_city) out.location_city = c.location_city;
  if (c.location_state) out.location_state = c.location_state;
  if (c.remote_preference) out.remote_preference = c.remote_preference;
  if (c.location_scope) out.location_scope = c.location_scope;
  if (c.looking_for) out.looking_for = c.looking_for;
  return out;
}
