"use client";

/**
 * CareerKickoffFlow — guided first-run flow rendered inside chat, right after
 * onboarding. Three steps, all backed by existing APIs:
 *
 *   1. Analysis — show what Aarya extracted from the CV
 *   2. Path      — AI proposes top directions; candidate picks ONE preferred path
 *   3. Review    — confirm the search brief; parent sends it through normal chat
 *
 * On completion the parent (ChatInterface) starts the normal Aarya chat search,
 * so the candidate lands in a live conversation with job cards.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, Loader2, Sparkles } from "@/components/brand/icons";
import {
  fetchCareerPath,
  fetchCareerIntelligence,
  generateCareerPath,
  prioritizeCareerPath,
  type CareerIntelligence,
  type CareerPath,
} from "@/lib/api/career";
import { fetchMyProfile, type MyProfileData } from "@/lib/api/profile";
import {
  clearCareerKickoffProgress,
  readCareerKickoffProgress,
  saveCareerKickoffProgress,
  type KickoffProgressStep,
} from "@/lib/auth/career-kickoff";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { BTN_CHIP, BTN_CHIP_ACTIVE, BTN_GHOST } from "@/lib/button-classes";
import { useAiOperations } from "@/components/providers/AiOperationsProvider";
import { resolveReadyOrAccepted } from "@/lib/operations/resolve";
import { AI_OPERATION_KINDS } from "@/lib/operations/kinds";

const MAX_OPTIONS = 3;
const TOTAL_STEPS = 3;

type PathOption = {
  title: string;
  rationale: string | null;
  custom?: boolean;
};

type Step = "loading" | "analysis" | "paths_loading" | "paths" | "review" | "error";

export type KickoffResult = {
  preferredTitle: string;
  selectedTitles: string[];
  prompt: string;
};

/** Build kickoff options from Intelligence mobility (same order as Profile tab). */
function buildOptionsFromIntelligence(
  intelligence: CareerIntelligence | null | undefined,
): PathOption[] {
  const adjacent = intelligence?.mobility?.adjacent_roles ?? [];
  if (adjacent.length === 0) return [];

  const ranked = [...adjacent]
    .filter((row) => row.role?.trim())
    .sort(
      (a, b) =>
        (b.feasibility_score ?? 0) - (a.feasibility_score ?? 0),
    )
    .slice(0, MAX_OPTIONS);

  return ranked.map((row) => {
    const gaps = (row.skill_gap ?? []).filter(Boolean).slice(0, 3);
    const parts: string[] = [];
    if (row.feasibility_score != null) {
      parts.push(`${row.feasibility_score}% fit`);
    }
    if (row.time_required?.trim()) {
      parts.push(`≈ ${row.time_required.trim()}`);
    }
    if (gaps.length > 0) {
      parts.push(`Skills to build: ${gaps.join(", ")}`);
    }
    return {
      title: row.role.trim(),
      rationale: parts.join(" · ") || "Adjacent role from your Intelligence profile",
    };
  });
}

/** Build up to 3 distinct options from path steps (next/future) + target titles. */
function buildOptions(path: CareerPath, currentTitle?: string | null): PathOption[] {
  const options: PathOption[] = [];
  const seen = new Set<string>();
  const push = (title: string, rationale: string | null) => {
    const t = title.trim();
    if (!t || seen.has(t.toLowerCase()) || options.length >= MAX_OPTIONS) return;
    seen.add(t.toLowerCase());
    options.push({ title: t, rationale });
  };
  if (currentTitle?.trim()) {
    push(currentTitle.trim(), "Your current role — search similar openings");
  }
  for (const s of path.steps) {
    if (s.level === "next" || s.level === "future") {
      push(s.title, s.rationale);
    }
  }
  for (const t of path.target_titles) push(t, null);
  return options;
}

function resolveKickoffOptions(
  intelligence: CareerIntelligence | null | undefined,
  path: CareerPath | null | undefined,
  currentTitle?: string | null,
): PathOption[] {
  const fromIntel = buildOptionsFromIntelligence(intelligence);
  if (fromIntel.length > 0) return fromIntel;
  return path ? buildOptions(path, currentTitle) : [];
}

function defaultPreferredTitle(
  options: PathOption[],
  savedPick?: string,
  prioritizedTitle?: string | null,
): string {
  if (savedPick?.trim()) return savedPick.trim();
  if (prioritizedTitle?.trim()) return prioritizedTitle.trim();
  return options[0]?.title ?? "";
}

function buildRoleSearchPrompt(profile: MyProfileData | null, title: string): string {
  const candidate = profile?.candidate;
  const segments = [`Find ${title.trim() || "roles"}`];
  const city = candidate?.location_city?.trim();
  if (city) segments.push(`in ${city}`);

  const years =
    typeof candidate?.years_experience === "number" && candidate.years_experience > 0
      ? candidate.years_experience
      : null;
  const skills = (candidate?.skills ?? [])
    .map((skill) => skill.trim())
    .filter(Boolean)
    .slice(0, 6);

  if (years && skills.length > 0) {
    segments.push(
      `for someone with ${years}+ years of experience matching my skills in ${skills.join(", ")}`,
    );
  } else if (years) {
    segments.push(`for someone with ${years}+ years of experience`);
  } else if (skills.length > 0) {
    segments.push(`matching my skills in ${skills.join(", ")}`);
  }

  return `${segments.join(" ")}.`;
}

function buildAnalysisRows(profile: MyProfileData | null) {
  const c = profile?.candidate;
  const cleanLocation = (raw: string | null | undefined) => {
    const v = (raw ?? "").trim();
    if (!v) return null;
    // Display-side guard for legacy bad parses like "nayak Bengaluru".
    const parts = v.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      const tail = parts.slice(1).join(" ");
      if (/(^|[\s,])bengaluru([\s,]|$)/i.test(v) && parts[0] === parts[0].toLowerCase()) {
        return tail;
      }
    }
    return v;
  };

  const cleanSkill = (raw: string) => {
    const v = raw.trim();
    if (!v) return "";
    if (/https?:\/\//i.test(v) || /www\./i.test(v)) return "";
    // If it's all-lowercase words, title-case it for readability.
    if (v === v.toLowerCase()) return v.replace(/\b\w/g, (m) => m.toUpperCase());
    return v;
  };

  const skills = (c?.skills ?? [])
    .map((s) => cleanSkill(s))
    .filter(Boolean);
  return [
    {
      label: "Current role",
      value: c?.current_title
        ? `${c.current_title}${c.current_company ? ` · ${c.current_company}` : ""}`
        : null,
    },
    { label: "Experience", value: c?.years_experience ? `${c.years_experience} years` : null },
    { label: "Location", value: cleanLocation(c?.location_city ?? null) },
    { label: "Skills", value: skills.length > 0 ? skills.slice(0, 8).join(", ") : null },
    { label: "Looking for", value: c?.looking_for?.trim() || null },
    { label: "CV", value: profile?.resume_filename ?? null },
  ].filter((r) => r.value);
}

export function CareerKickoffFlow({
  userId,
  onComplete,
  onSkip,
  onStepArchived,
}: {
  userId?: string | null;
  onComplete: (result: KickoffResult) => void;
  onSkip: () => void;
  onStepArchived?: (payload: { step: 1 | 2 | 3; content: string }) => void;
}) {
  const [step, setStep] = useState<Step>("loading");
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [options, setOptions] = useState<PathOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [customTitle, setCustomTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const archivedStepsRef = useRef<Set<1 | 2 | 3>>(new Set());
  const { trackAndWait } = useAiOperations();

  const persistProgress = useCallback(
    (
      nextStep: KickoffProgressStep,
      nextSelected: string[],
      nextOptions: PathOption[],
    ) => {
      saveCareerKickoffProgress(
        {
          step: nextStep,
          selected: nextSelected,
          options: nextOptions,
        },
        userId ?? undefined,
      );
    },
    [userId],
  );

  const archiveStepOnce = useCallback(
    (payload: { step: 1 | 2 | 3; content: string }) => {
      if (archivedStepsRef.current.has(payload.step)) return;
      archivedStepsRef.current.add(payload.step);
      onStepArchived?.(payload);
    },
    [onStepArchived],
  );

  // ── Load: profile + resume in-progress kickoff from session/API ─────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, path, intelligence, saved] = await Promise.all([
          fetchMyProfile().catch(() => null),
          fetchCareerPath().catch(() => null),
          fetchCareerIntelligence().catch(() => null),
          Promise.resolve(readCareerKickoffProgress(userId ?? undefined)),
        ]);
        if (cancelled) return;
        setProfile(p);

        const currentTitle = p?.candidate?.current_title ?? null;
        const kickoffOptions = resolveKickoffOptions(intelligence, path, currentTitle);
        const intelTop = buildOptionsFromIntelligence(intelligence)[0]?.title ?? "";
        const pathMismatch =
          Boolean(path?.prioritized_title && intelTop) &&
          path!.prioritized_title!.toLowerCase() !== intelTop.toLowerCase();
        const defaultPick = defaultPreferredTitle(
          kickoffOptions,
          saved?.selected[0],
          pathMismatch ? null : path?.prioritized_title,
        );

        if (path?.prioritized_title && !pathMismatch) {
          const pick = path.prioritized_title;
          const opts = saved?.options.length ? saved.options : kickoffOptions;
          setOptions(opts.length ? opts : [{ title: pick, rationale: null }]);
          setSelected([pick]);
          setStep("review");
          persistProgress("review", [pick], opts.length ? opts : [{ title: pick, rationale: null }]);
          return;
        }

        if (saved?.step === "review" && saved.selected[0]) {
          setOptions(saved.options.length ? saved.options : kickoffOptions);
          setSelected(saved.selected);
          setStep("review");
          return;
        }

        if (saved?.step === "paths" && saved.options.length > 0) {
          setOptions(saved.options);
          setSelected(
            saved.selected.length > 0 ? saved.selected : [saved.options[0].title],
          );
          setStep("paths");
          return;
        }

        if (kickoffOptions.length > 0) {
          const pick = defaultPick || kickoffOptions[0].title;
          setOptions(kickoffOptions);
          setSelected(pick ? [pick] : []);
          setStep("paths");
          persistProgress("paths", pick ? [pick] : [], kickoffOptions);
          return;
        }

        setStep("analysis");
        persistProgress("analysis", [], []);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Couldn't load your profile.");
        setStep("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [persistProgress, userId]);

  const toggle = useCallback(
    (title: string) => {
      setSelected([title]);
      persistProgress(step === "review" ? "review" : "paths", [title], options);
    },
    [options, persistProgress, step],
  );

  const addCustom = useCallback(() => {
    const t = customTitle.trim();
    if (!t) return;
    setOptions((prev) => {
      if (prev.some((o) => o.title.toLowerCase() === t.toLowerCase())) return prev;
      const next = [...prev, { title: t, rationale: "Your own direction", custom: true }];
      setSelected([t]);
      persistProgress(step === "review" ? "review" : "paths", [t], next);
      return next;
    });
    setCustomTitle("");
  }, [customTitle, persistProgress, step]);

  const c = profile?.candidate;
  const analysisRows = useMemo(() => buildAnalysisRows(profile), [profile]);
  const reviewRows = useMemo(
    () =>
      [
        { label: "Current role", value: c?.current_title ? `${c.current_title}${c.current_company ? ` · ${c.current_company}` : ""}` : null },
        { label: "Experience", value: c?.years_experience ? `${c.years_experience} years` : null },
        { label: "Location", value: c?.location_city ?? null },
        { label: "Skills", value: (c?.skills ?? []).slice(0, 6).join(", ") || null },
        { label: "Preferred path", value: selected[0] ?? null },
        { label: "Aarya prompt", value: selected[0] ? buildRoleSearchPrompt(profile, selected[0]) : null },
      ].filter((r) => r.value),
    [c, selected, profile],
  );

  // ── Step 1 confirm: resume analysis looks good ─────────────────────────────
  async function confirmAnalysis() {
    if (busy) return;
    setBusy(true);
    setError(null);

    const cached = readCareerKickoffProgress(userId ?? undefined);
    if (cached?.options.length && cached.step !== "analysis") {
      setOptions(cached.options);
      setSelected(cached.selected.length > 0 ? cached.selected : [cached.options[0].title]);
      archiveStepOnce({
        step: 1,
        content:
          "**Step 1 of 3** · Resume analysis\n\n" +
          analysisRows.map((r) => `**${r.label}:** ${r.value}`).join("\n"),
      });
      setStep("paths");
      setBusy(false);
      return;
    }

    setStep("paths_loading");
    try {
      const outcome = await generateCareerPath();
      const path = await resolveReadyOrAccepted(
        outcome,
        trackAndWait,
        async () => {
          const next = await fetchCareerPath();
          if (!next) throw new Error("No career path returned");
          return next;
        },
        { kind: AI_OPERATION_KINDS.careerPathGenerate },
      );
      const intelligence = await fetchCareerIntelligence().catch(() => null);
      const opts = resolveKickoffOptions(
        intelligence,
        path,
        profile?.candidate?.current_title,
      );
      setOptions(opts);
      const pickTitle = defaultPreferredTitle(opts);
      const pick = pickTitle ? [pickTitle] : [];
      setSelected(pick);
      persistProgress("paths", pick, opts);
      archiveStepOnce({
        step: 1,
        content:
          "**Step 1 of 3** · Resume analysis\n\n" +
          analysisRows.map((r) => `**${r.label}:** ${r.value}`).join("\n"),
      });
      setStep("paths");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't map career paths from your CV.",
      );
      setStep("analysis");
    } finally {
      setBusy(false);
    }
  }

  // ── Step 2 confirm: save paths ──────────────────────────────────────────────
  async function confirmPaths() {
    if (busy || selected.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await prioritizeCareerPath(selected[0], selected);
      persistProgress("review", selected, options);
      archiveStepOnce({
        step: 2,
        content:
          "**Step 2 of 3** · Career path\n\n" +
          selected.map((t, i) => `${i === 0 ? "Preferred: " : "Also search: "}${t}`).join("\n"),
      });
      setStep("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your career path.");
    } finally {
      setBusy(false);
    }
  }

  // ── Step 3 confirm: ask Aarya through the normal chat search path ───────────
  function confirmReview() {
    if (busy || selected.length === 0) return;
    setBusy(true);
    setError(null);
    const reviewLines = reviewRows.map((r) => `**${r.label}:** ${r.value}`).join("\n");
    archiveStepOnce({
      step: 3,
      content: `**Step 3 of 3** · Final search brief\n\n${reviewLines}`,
    });
    clearCareerKickoffProgress();
    onComplete({
      preferredTitle: selected[0],
      selectedTitles: selected,
      prompt: buildRoleSearchPrompt(profile, selected[0]),
    });
  }

  const stepIndex =
    step === "analysis" ? 1 : step === "paths" || step === "paths_loading" ? 2 : step === "review" ? 3 : undefined;

  // ── Render ──────────────────────────────────────────────────────────────────

  if (step === "loading") {
    return (
      <FlowShell>
        <div className="flex items-center gap-2.5 text-small text-ink-600">
          <Loader2 className="h-4 w-4 animate-spin text-ink-400" strokeWidth={1.75} />
          Loading your profile from your CV…
        </div>
      </FlowShell>
    );
  }

  if (step === "paths_loading") {
    return (
      <FlowShell stepIndex={2}>
        <div className="flex items-center gap-2.5 text-small text-ink-600">
          <Loader2 className="h-4 w-4 animate-spin text-ink-400" strokeWidth={1.75} />
          Mapping career paths from your experience…
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

  return (
    <FlowShell stepIndex={stepIndex}>
      {step === "analysis" && (
        <>
          <p className="text-small text-ink-800 leading-relaxed">
            I&apos;ve analysed your CV. Here&apos;s what I&apos;ll use to map career
            paths and rank jobs — check it looks right before we continue.
          </p>
          <div className="rounded-lg border border-ink-100 bg-paper-0 divide-y divide-ink-100">
            {analysisRows.map((row) => (
              <div key={row.label} className="flex items-start gap-3 px-3 py-2">
                <span className="w-28 shrink-0 text-micro font-medium uppercase tracking-wide text-ink-400 pt-0.5">
                  {row.label}
                </span>
                <span className="text-small text-ink-900 min-w-0">{row.value}</span>
              </div>
            ))}
          </div>
          {error && <FlowError message={error} />}
          <Button
            variant="primary"
            size="md"
            fullWidth
            loading={busy}
            onClick={() => void confirmAnalysis()}
          >
            Continue to career paths
          </Button>
          <button
            type="button"
            onClick={onSkip}
            className="w-full text-center text-small text-ink-500 hover:text-ink-900 transition-colors"
          >
            Skip — show me jobs now
          </button>
        </>
      )}

      {step === "paths" && (
        <>
          <p className="text-small text-ink-800 leading-relaxed">
            These paths match your Intelligence profile — same order and fit
            scores as the Profile tab. Pick{" "}
            <span className="font-medium">one preferred path</span> (or type your
            own) — I&apos;ll automatically search similar titles too.
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
            One path, wide net — similar job titles are searched automatically.
          </p>
          {error && <FlowError message={error} />}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              fullWidth
              loading={busy}
              disabled={selected.length === 0 || busy}
              onClick={() => void confirmPaths()}
              className="flex-1"
            >
              Continue to review
            </Button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                persistProgress("analysis", selected, options);
                setStep("analysis");
              }}
              className="text-small text-ink-500 hover:text-ink-900 transition-colors px-2 shrink-0"
            >
              Back
            </button>
          </div>
          <button
            type="button"
            onClick={onSkip}
            className="w-full text-center text-small text-ink-500 hover:text-ink-900 transition-colors"
          >
            Skip — just chat
          </button>
        </>
      )}

      {step === "review" && (
        <>
          <p className="text-small text-ink-800 leading-relaxed">
            Last check — this is the search brief I&apos;ll send to Aarya now.
            It uses your CV, location, and selected career path.
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
          {error && <FlowError message={error} />}
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              loading={busy}
              onClick={confirmReview}
              className="flex-1"
            >
              Find matching jobs
            </Button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                persistProgress("paths", selected, options);
                setStep("paths");
              }}
              className="text-small text-ink-500 hover:text-ink-900 transition-colors px-2 shrink-0"
            >
              Back
            </button>
          </div>
          <button
            type="button"
            onClick={onSkip}
            className="w-full text-center text-small text-ink-500 hover:text-ink-900 transition-colors"
          >
            Skip — just chat
          </button>
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
          Aarya <span className="font-normal text-ink-500">· getting started</span>
        </p>
        {stepIndex != null && (
          <span className="ml-auto rounded border border-accent/40 bg-accent/15 px-2 py-0.5 text-micro font-semibold text-accent">
            Step {stepIndex} of {TOTAL_STEPS}
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
