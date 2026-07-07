"use client";

/**
 * CareerKickoffFlow — guided first-run flow rendered inside chat, right after
 * onboarding. Three steps, all backed by existing APIs:
 *
 *   1. Paths   — AI proposes the top 3 career paths (pre-selected);
 *                multi-select + free-text "other". First selected = preferred.
 *   2. Package — expected CTC range for the candidate's market.
 *   3. Review  — everything Aarya will use to search; confirm saves it all,
 *                fires per-path resume generation, and runs the job search
 *                for the preferred path.
 *
 * On completion the parent (ChatInterface) appends the jobs as a normal
 * assistant message, so the candidate lands in a live conversation.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Loader2, Sparkles } from "@/components/brand/icons";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  fetchCareerPath,
  findJobsForPath,
  generateCareerPath,
  generateCareerPathResumes,
  prioritizeCareerPath,
  type CareerPath,
} from "@/lib/api/career";
import { fetchMyProfile, type MyProfileData } from "@/lib/api/profile";
import type { MatchedJob } from "@/lib/api/matches";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { BTN_CHIP, BTN_CHIP_ACTIVE, BTN_GHOST } from "@/lib/button-classes";

const MAX_OPTIONS = 3;
const MAX_SELECTED = 3;

type PathOption = {
  title: string;
  rationale: string | null;
  custom?: boolean;
};

type Step = "loading" | "paths" | "package" | "review" | "finishing" | "error";

export type KickoffResult = {
  preferredTitle: string;
  selectedTitles: string[];
  jobs: MatchedJob[];
  refreshing: boolean;
};

/** Build up to 3 distinct options from path steps (next/future) + target titles. */
function buildOptions(path: CareerPath): PathOption[] {
  const options: PathOption[] = [];
  const seen = new Set<string>();
  const push = (title: string, rationale: string | null) => {
    const t = title.trim();
    if (!t || seen.has(t.toLowerCase()) || options.length >= MAX_OPTIONS) return;
    seen.add(t.toLowerCase());
    options.push({ title: t, rationale });
  };
  for (const s of path.steps) {
    if (s.level === "next" || s.level === "future") {
      push(s.title, s.rationale);
    }
  }
  for (const t of path.target_titles) push(t, null);
  return options;
}

function currencyHint(market?: string): { label: string; placeholderMin: string; placeholderMax: string } {
  switch (market) {
    case "US":
      return { label: "USD per year (thousands)", placeholderMin: "e.g. 120", placeholderMax: "e.g. 160" };
    case "GB":
      return { label: "GBP per year (thousands)", placeholderMin: "e.g. 60", placeholderMax: "e.g. 85" };
    case "AT":
    case "DE":
    case "FR":
    case "NL":
      return { label: "EUR per year (thousands)", placeholderMin: "e.g. 55", placeholderMax: "e.g. 80" };
    case "CH":
      return { label: "CHF per year (thousands)", placeholderMin: "e.g. 90", placeholderMax: "e.g. 130" };
    case "AE":
      return { label: "AED per year (thousands)", placeholderMin: "e.g. 180", placeholderMax: "e.g. 280" };
    case "AU":
      return { label: "AUD per year (thousands)", placeholderMin: "e.g. 90", placeholderMax: "e.g. 140" };
    case "CA":
      return { label: "CAD per year (thousands)", placeholderMin: "e.g. 80", placeholderMax: "e.g. 120" };
    case "SG":
      return { label: "SGD per year (thousands)", placeholderMin: "e.g. 70", placeholderMax: "e.g. 110" };
    default:
      return { label: "INR lakhs per annum (LPA)", placeholderMin: "e.g. 18", placeholderMax: "e.g. 25" };
  }
}

export function CareerKickoffFlow({
  onComplete,
  onSkip,
  onStepArchived,
}: {
  onComplete: (result: KickoffResult) => void;
  onSkip: () => void;
  onStepArchived?: (payload: { step: 1 | 2 | 3; content: string }) => void;
}) {
  const [step, setStep] = useState<Step>("loading");
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [options, setOptions] = useState<PathOption[]>([]);
  // Selection order matters: first = preferred.
  const [selected, setSelected] = useState<string[]>([]);
  const [customTitle, setCustomTitle] = useState("");
  const [ctcMin, setCtcMin] = useState("");
  const [ctcMax, setCtcMax] = useState("");
  const [busy, setBusy] = useState(false);
  const [finishStatus, setFinishStatus] = useState("");

  // ── Load: profile + career path (generate on first run) ────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, existing] = await Promise.all([
          fetchMyProfile().catch(() => null),
          fetchCareerPath().catch(() => null),
        ]);
        const path = existing ?? (await generateCareerPath());
        if (cancelled) return;
        setProfile(p);
        if (p?.candidate?.expected_ctc_min) setCtcMin(String(p.candidate.expected_ctc_min));
        if (p?.candidate?.expected_ctc_max) setCtcMax(String(p.candidate.expected_ctc_max));
        const opts = buildOptions(path);
        setOptions(opts);
        // AI pre-selects the top 3 — the candidate can freely change this.
        setSelected(opts.slice(0, MAX_SELECTED).map((o) => o.title));
        setStep("paths");
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Couldn't analyse your CV for career paths.",
        );
        setStep("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = useCallback((title: string) => {
    setSelected((prev) => {
      if (prev.includes(title)) return prev.filter((t) => t !== title);
      if (prev.length >= MAX_SELECTED) return prev; // hard cap — uncheck one first
      return [...prev, title];
    });
  }, []);

  const addCustom = useCallback(() => {
    const t = customTitle.trim();
    if (!t) return;
    setOptions((prev) => {
      if (prev.some((o) => o.title.toLowerCase() === t.toLowerCase())) return prev;
      return [...prev, { title: t, rationale: "Your own direction", custom: true }];
    });
    setSelected((prev) => {
      if (prev.some((x) => x.toLowerCase() === t.toLowerCase())) return prev;
      if (prev.length >= MAX_SELECTED) return prev;
      return [...prev, t];
    });
    setCustomTitle("");
  }, [customTitle]);

  const c = profile?.candidate;
  const hint = currencyHint(profile?.user?.market);
  const reviewRows = useMemo(
    () =>
      [
        { label: "Current role", value: c?.current_title ? `${c.current_title}${c.current_company ? ` · ${c.current_company}` : ""}` : null },
        { label: "Experience", value: c?.years_experience ? `${c.years_experience} years` : null },
        { label: "Location", value: c?.location_city ?? null },
        { label: "Skills", value: (c?.skills ?? []).slice(0, 6).join(", ") || null },
        { label: "Career paths", value: selected.join("  ·  ") || null },
        { label: "Preferred path", value: selected[0] ?? null },
        {
          label: "Expected package",
          value:
            ctcMin || ctcMax
              ? `${ctcMin || "—"}–${ctcMax || "—"} (${hint.label})`
              : null,
        },
      ].filter((r) => r.value),
    [c, selected, ctcMin, ctcMax, hint.label],
  );

  // ── Step 1 confirm: save paths ──────────────────────────────────────────────
  async function confirmPaths() {
    if (busy || selected.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await prioritizeCareerPath(selected[0], selected);
      onStepArchived?.({
        step: 1,
        content:
          "**Step 1 of 3** · Career paths\n\n" +
          selected.map((t, i) => `${i === 0 ? "⭐ " : "• "}${t}`).join("\n"),
      });
      setStep("package");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your career paths.");
    } finally {
      setBusy(false);
    }
  }

  // ── Step 2 confirm: save CTC ────────────────────────────────────────────────
  async function confirmPackage() {
    if (busy) return;
    const min = Number.parseInt(ctcMin, 10);
    const max = Number.parseInt(ctcMax, 10);
    const payload: Record<string, number> = {};
    if (Number.isFinite(min) && min > 0) payload.expected_ctc_min = min;
    if (Number.isFinite(max) && max > 0) payload.expected_ctc_max = max;
    if (payload.expected_ctc_min && payload.expected_ctc_max && payload.expected_ctc_max < payload.expected_ctc_min) {
      setError("Max should be at least the min.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (Object.keys(payload).length > 0) {
        const res = await apiAuthFetch("/api/v1/me/profile", {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const data = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(data.detail ?? "Couldn't save your expected package.");
        }
        // Refresh so the review step shows what was actually saved.
        const p = await fetchMyProfile({ force: true }).catch(() => profile);
        if (p) setProfile(p);
      }
      const pkgLabel =
        ctcMin || ctcMax
          ? `${ctcMin || "—"} – ${ctcMax || "—"} ${currencyHint(profile?.user?.market).label}`
          : "Not set";
      onStepArchived?.({
        step: 2,
        content: `**Step 2 of 3** · Expected package\n\n${pkgLabel}`,
      });
      setStep("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your expected package.");
    } finally {
      setBusy(false);
    }
  }

  // ── Step 3 confirm: resumes + job search ────────────────────────────────────
  async function confirmReview() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const reviewLines = reviewRows.map((r) => `**${r.label}:** ${r.value}`).join("\n");
    onStepArchived?.({
      step: 3,
      content: `**Step 3 of 3** · Review\n\n${reviewLines}`,
    });
    setStep("finishing");
    try {
      // Per-path tailored resumes — only when the candidate opted in (Settings).
      if (profile?.candidate?.tailored_resume_enabled) {
        setFinishStatus("Generating a tailored resume for each path…");
        void generateCareerPathResumes().catch(() => {
          /* non-fatal — resumes can be generated later from settings */
        });
      }

      setFinishStatus(`Searching ${selected[0]} roles for you…`);
      const result = await findJobsForPath();
      onComplete({
        preferredTitle: selected[0],
        selectedTitles: selected,
        jobs: result.jobs,
        refreshing: result.refreshing,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start the job search.");
      setStep("review");
    } finally {
      setBusy(false);
    }
  }

  const stepIndex =
    step === "paths" ? 1 : step === "package" ? 2 : step === "review" ? 3 : undefined;

  // ── Render ──────────────────────────────────────────────────────────────────

  if (step === "loading") {
    return (
      <FlowShell>
        <div className="flex items-center gap-2.5 text-small text-ink-600">
          <Loader2 className="h-4 w-4 animate-spin text-ink-400" strokeWidth={1.75} />
          Analysing your CV and mapping career paths…
        </div>
      </FlowShell>
    );
  }

  if (step === "error") {
    return (
      <FlowShell>
        <p className="text-small text-ink-700">{error}</p>
        <div className="flex gap-2 pt-1">
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
            Try again
          </Button>
          <button
            type="button"
            onClick={onSkip}
            className="text-small text-ink-500 hover:text-ink-900 transition-colors px-2"
          >
            Skip — just chat
          </button>
        </div>
      </FlowShell>
    );
  }

  if (step === "finishing") {
    return (
      <FlowShell>
        <div className="flex items-center gap-2.5 text-small text-ink-600">
          <Loader2 className="h-4 w-4 animate-spin text-ink-400" strokeWidth={1.75} />
          {finishStatus || "Setting things up…"}
        </div>
      </FlowShell>
    );
  }

  return (
    <FlowShell stepIndex={stepIndex}>
      {step === "paths" && (
        <>
          <p className="text-small text-ink-800 leading-relaxed">
            Based on your CV, these are the strongest career paths for you. I&apos;ve
            pre-selected my top 3 — tap to change, or add your own. Your{" "}
            <span className="font-medium">first pick becomes the preferred path</span>{" "}
            I search first.
          </p>
          <div className="space-y-1.5">
            {options.map((opt) => {
              const idx = selected.indexOf(opt.title);
              const isSelected = idx >= 0;
              return (
                <button
                  key={opt.title}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => toggle(opt.title)}
                  className={cn(
                    "w-full flex items-start gap-2.5 px-3 py-2.5 text-left",
                    isSelected ? BTN_CHIP_ACTIVE : BTN_CHIP,
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border-2",
                      isSelected
                        ? "border-black bg-black text-accent"
                        : "border-black/40 bg-transparent text-transparent",
                    )}
                    aria-hidden
                  >
                    {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-small font-semibold text-black">{opt.title}</span>
                      {idx === 0 && (
                        <span className="text-micro font-semibold uppercase tracking-wide text-black/70">
                          Preferred
                        </span>
                      )}
                    </span>
                    {opt.rationale && (
                      <span className="block text-micro text-black/60 leading-snug mt-0.5">
                        {opt.rationale}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={customTitle}
              onChange={(e) => setCustomTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addCustom();
                }
              }}
              placeholder="Other — type your own path"
              className="flex-1 rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent-ring"
            />
            <button
              type="button"
              onClick={addCustom}
              className={cn(BTN_GHOST, "px-3 py-2 text-small shrink-0")}
            >
              Add
            </button>
          </div>
          <p className="text-micro text-ink-400">
            {selected.length}/{MAX_SELECTED} selected
            {selected.length >= MAX_SELECTED ? " — uncheck one to swap" : ""}
          </p>
          {error && <FlowError message={error} />}
          <Button
            variant="primary"
            size="md"
            fullWidth
            loading={busy}
            disabled={selected.length === 0 || busy}
            onClick={() => void confirmPaths()}
          >
            Continue
          </Button>
        </>
      )}

      {step === "package" && (
        <>
          <p className="text-small text-ink-800 leading-relaxed">
            What package are you targeting? I&apos;ll use this to filter salary-fit
            roles — you can change it anytime in Settings.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label htmlFor="kickoff-ctc-min" className="text-small font-medium text-ink-700">
                Minimum
              </label>
              <input
                id="kickoff-ctc-min"
                type="number"
                inputMode="numeric"
                min={0}
                value={ctcMin}
                onChange={(e) => setCtcMin(e.target.value)}
                placeholder={hint.placeholderMin}
                className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent-ring"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="kickoff-ctc-max" className="text-small font-medium text-ink-700">
                Maximum
              </label>
              <input
                id="kickoff-ctc-max"
                type="number"
                inputMode="numeric"
                min={0}
                value={ctcMax}
                onChange={(e) => setCtcMax(e.target.value)}
                placeholder={hint.placeholderMax}
                className="w-full rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent-ring"
              />
            </div>
          </div>
          <p className="text-micro text-ink-400">{hint.label}</p>
          {error && <FlowError message={error} />}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              loading={busy}
              onClick={() => void confirmPackage()}
              className="flex-1"
            >
              Continue
            </Button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setStep("review");
              }}
              className="text-small text-ink-500 hover:text-ink-900 transition-colors px-2 shrink-0"
            >
              Skip
            </button>
          </div>
        </>
      )}

      {step === "review" && (
        <>
          <p className="text-small text-ink-800 leading-relaxed">
            Last check — this is everything I&apos;ll use to find your jobs. If
            something&apos;s off, fix it in your profile later; otherwise let&apos;s go.
          </p>
          <div className="rounded-lg border border-ink-100 bg-paper-1 divide-y divide-ink-100">
            {reviewRows.map((row) => (
              <div key={row.label} className="flex items-start gap-3 px-3 py-2">
                <span className="w-28 shrink-0 text-micro font-medium uppercase tracking-wide text-ink-400 pt-0.5">
                  {row.label}
                </span>
                <span className="text-small text-ink-900 min-w-0">{row.value}</span>
              </div>
            ))}
          </div>
          {profile?.candidate?.tailored_resume_enabled ? (
            <p className="text-micro text-ink-400">
              On confirm I&apos;ll also generate a tailored resume for each of your
              selected paths.
            </p>
          ) : null}
          {error && <FlowError message={error} />}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              loading={busy}
              onClick={() => void confirmReview()}
              className="flex-1"
            >
              Continue — show jobs
            </Button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setStep("paths");
              }}
              className="text-small text-ink-500 hover:text-ink-900 transition-colors px-2 shrink-0"
            >
              Back
            </button>
          </div>
        </>
      )}
    </FlowShell>
  );
}

// ── Shell + bits ───────────────────────────────────────────────────────────────

function FlowShell({
  children,
  stepIndex,
}: {
  children: React.ReactNode;
  stepIndex?: number;
}) {
  return (
    <div className="w-full animate-fade-in">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-full bg-ink-900 flex items-center justify-center shrink-0">
          <Sparkles className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
        </div>
        <p className="text-small font-semibold text-ink-900">
          Aarya <span className="font-normal text-ink-500">· career kickoff</span>
        </p>
        {stepIndex != null && (
          <span className="ml-auto rounded border border-accent/40 bg-accent/15 px-2 py-0.5 text-micro font-semibold text-accent">
            Step {stepIndex} of 3
          </span>
        )}
      </div>
      <div className="rounded-lg border border-ink-100 bg-paper-1 p-4 shadow-1 space-y-3.5">
        {children}
      </div>
    </div>
  );
}

function FlowError({ message }: { message: string }) {
  return (
    <p className="text-small text-destructive rounded-lg border border-destructive/30 bg-destructive-bg px-3 py-2">
      {message}
    </p>
  );
}
