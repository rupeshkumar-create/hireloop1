"use client";

/**
 * CareerIntelligencePanel — the candidate's 24-layer Career Intelligence.
 *
 * Layout:
 *   1. A summary hero (archetype, market value, likely next role, completeness)
 *      so the headline insight is visible without scrolling.
 *   2. Four collapsible groups that hold the deep layers — collapsed by default
 *      (except "Who you are") so the screen isn't a 20-card wall.
 *
 * Loads stored intelligence on mount (GET /career/intelligence). If none exists,
 * auto-starts generation and polls until ready — no manual click. "Refresh"
 * recomputes on demand (POST /career/intelligence/generate).
 *
 * Every layer renders conditionally — the engine fills what it can from resume /
 * LinkedIn / chat, so sparse profiles show fewer sections, and empty groups are
 * skipped entirely.
 */

import { useEffect, useState } from "react";
import { Brain, ChevronDown, Loader2, RefreshCw } from "lucide-react";
import { Badge, Button, Card, CardBody } from "@/components/ui";
import { cn } from "@/lib/utils";
import { getCachedProfile } from "@/lib/api/profile";
import { marketByCode, type MarketCode } from "@/lib/markets";
import {
  formatCompensationAmount,
  formatSalaryRange,
} from "@/lib/salary";
import {
  fetchCareerIntelligence,
  generateCareerIntelligence,
  type CareerIntelligence,
  type HardSkill,
  type MobilityOption,
  type Prediction,
} from "@/lib/api/career";

// ── Small presentational helpers ────────────────────────────────────────────

/** Horizontal 0–100 meter. */
function ScoreBar({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
}) {
  if (value === null || value === undefined) return null;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-micro text-ink-600 capitalize">
          {label.replace(/_/g, " ")}
        </span>
        <span className="text-micro font-medium text-ink-900 tabular-nums">
          {value}
          {suffix ?? ""}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-ink-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-ink-900 transition-all duration-base"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

/** A wrapped list of muted chips. */
function Chips({ items }: { items: (string | null | undefined)[] }) {
  const clean = items.filter((s): s is string => Boolean(s && s.trim()));
  if (clean.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {clean.map((s, i) => (
        <Badge key={`${s}-${i}`}>{s}</Badge>
      ))}
    </div>
  );
}

/** Label / value row for plain facts. */
function Fact({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-micro text-ink-500 capitalize shrink-0">
        {label.replace(/_/g, " ")}
      </span>
      <span className="text-small text-ink-900 text-right">{value}</span>
    </div>
  );
}

/** A titled sub-block within a collapsible group (not its own card). */
function Layer({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2.5">
      <div>
        <h4 className="text-small font-semibold text-ink-900">{title}</h4>
        {description && (
          <p className="text-micro text-ink-500 mt-0.5 leading-relaxed">
            {description}
          </p>
        )}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function pct(n: number | null | undefined): string | null {
  if (n === null || n === undefined) return null;
  return `${Math.round(n)}%`;
}

// ── Composite sub-renderers ──────────────────────────────────────────────────

function MobilityList({
  items,
  onAskAarya,
}: {
  items?: MobilityOption[];
  onAskAarya?: (message: string) => void;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div className="space-y-2">
      {items.map((opt, i) => (
        <div
          key={`${opt.role}-${i}`}
          className="rounded-md border border-ink-100 px-3 py-2 space-y-1.5"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-small font-medium text-ink-900">
              {opt.role}
            </span>
            {opt.feasibility_score !== null &&
              opt.feasibility_score !== undefined && (
                <Badge tone="accent">{opt.feasibility_score}% fit</Badge>
              )}
          </div>
          {opt.time_required && (
            <p className="text-micro text-ink-500">≈ {opt.time_required}</p>
          )}
          {opt.skill_gap && opt.skill_gap.length > 0 && (
            <div className="space-y-1">
              <p className="text-micro text-ink-400">Skills to build:</p>
              <Chips items={opt.skill_gap} />
            </div>
          )}
          {onAskAarya && (
            <button
              type="button"
              onClick={() =>
                onAskAarya(
                  `Show me current roles for "${opt.role}" in my market and what it would take for me to move into it.`,
                )
              }
              className="text-micro font-medium text-accent hover:underline"
            >
              Explore this move →
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function PredictionRow({
  label,
  pred,
}: {
  label: string;
  pred?: Prediction | null;
}) {
  if (!pred || (!pred.outcome && pred.confidence === null)) return null;
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-ink-50 last:border-0">
      <div className="min-w-0">
        <p className="text-micro text-ink-500">{label}</p>
        <p className="text-small text-ink-900">{pred.outcome ?? "—"}</p>
      </div>
      {pred.confidence !== null && pred.confidence !== undefined && (
        <Badge tone="muted">{pct(pred.confidence)}</Badge>
      )}
    </div>
  );
}

function HardSkillList({ items }: { items?: HardSkill[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {items.map((s, i) => (
        <div
          key={`${s.skill}-${i}`}
          className="flex items-center justify-between gap-3 py-1 border-b border-ink-50 last:border-0"
        >
          <span className="text-small text-ink-900">{s.skill}</span>
          <div className="flex items-center gap-1.5 shrink-0">
            {s.years !== null && s.years !== undefined && (
              <span className="text-micro text-ink-400">{s.years}y</span>
            )}
            {s.proficiency && <Badge tone="muted">{s.proficiency}</Badge>}
            {s.recency && (
              <span className="text-micro text-ink-400">{s.recency}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Render a Record<string, number> as a set of score bars. */
function ScoreGrid({
  scores,
  suffix,
}: {
  scores?: Record<string, number> | null;
  suffix?: string;
}) {
  if (!scores) return null;
  const entries = Object.entries(scores).filter(
    ([, v]) => v !== null && v !== undefined && v !== 0,
  );
  if (entries.length === 0) return null;
  return (
    <div className="space-y-2.5">
      {entries
        .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
        .map(([k, v]) => (
          <ScoreBar key={k} label={k} value={v} suffix={suffix} />
        ))}
    </div>
  );
}

/** True when a score map has at least one non-zero value. */
function hasScoreMap(scores?: Record<string, number | null> | null): boolean {
  return !!scores && Object.values(scores).some((v) => v != null && v !== 0);
}

function hasMeaningfulFacts(obj: Record<string, unknown> | null | undefined): boolean {
  if (!obj) return false;
  return Object.entries(obj).some(([k, v]) => {
    if (k === "highlights" && Array.isArray(v)) return v.length > 0;
    if (v == null || v === "" || v === 0) return false;
    if (Array.isArray(v)) return v.length > 0;
    return true;
  });
}

// ── Collapsible group ────────────────────────────────────────────────────────

function CollapsibleGroup({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-ink-50 transition-colors duration-fast rounded-lg"
      >
        <span className="text-h3 text-ink-900">{title}</span>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-ink-400 transition-transform duration-fast shrink-0",
            open && "rotate-180",
          )}
          strokeWidth={1.5}
        />
      </button>
      {open && (
        <div className="px-5 pb-5 pt-1 space-y-5 border-t border-ink-100">
          {children}
        </div>
      )}
    </Card>
  );
}

/** One headline stat tile for the hero. */
function Stat({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) return null;
  return (
    <div className="rounded-md border border-ink-100 px-3 py-2">
      <p className="text-micro text-ink-400">{label}</p>
      <p className="text-small font-medium text-ink-900 mt-0.5 leading-snug">
        {value}
      </p>
    </div>
  );
}

// ── Loading skeleton (DESIGN.md: skeletons, not spinners) ─────────────────────

function IntelSkeleton() {
  return (
    <div className="space-y-4 animate-skeleton" aria-hidden>
      <Card>
        <CardBody className="space-y-4">
          <div className="flex gap-2">
            <div className="h-5 w-24 bg-ink-100 rounded-sm" />
            <div className="h-5 w-20 bg-ink-100 rounded-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-12 bg-ink-100 rounded-md" />
            ))}
          </div>
        </CardBody>
      </Card>
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <div className="flex items-center justify-between px-5 py-4">
            <div className="h-4 w-40 bg-ink-100 rounded" />
            <div className="h-4 w-4 bg-ink-100 rounded" />
          </div>
        </Card>
      ))}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────

function isPlaceholderIntelligence(i: CareerIntelligence | null): boolean {
  if (!i) return true;
  const hasLayers =
    Boolean(i.career_dna?.primary_archetype) ||
    Boolean(i.experience?.role_history?.length) ||
    Boolean(i.skills?.hard_skills?.length);
  return !hasLayers;
}

export function CareerIntelligencePanel({
  onAskAarya,
}: {
  /** Send a prompt to Aarya (closes the panel + runs the action in chat). */
  onAskAarya?: (message: string) => void;
} = {}) {
  const [intel, setIntel] = useState<CareerIntelligence | null>(null);
  const [market, setMarket] = useState<MarketCode>("IN");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [autoBuilding, setAutoBuilding] = useState(false);

  useEffect(() => {
    const m = getCachedProfile()?.user?.market;
    if (m) setMarket(marketByCode(m).code);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchCareerIntelligence();
        if (!cancelled) setIntel(data);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Couldn't load intelligence.",
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-build when nothing stored yet (or only a completeness stub) — kick off generation + poll.
  useEffect(() => {
    if (loading || (intel && !isPlaceholderIntelligence(intel))) return;

    setAutoBuilding(true);
    setError("");
    let attempts = 0;
    let cancelled = false;
    let generateStarted = false;

    const kickOffBuild = async () => {
      if (generateStarted) return;
      generateStarted = true;
      setGenerating(true);
      try {
        const built = await generateCareerIntelligence();
        if (!cancelled) setIntel(built);
      } catch {
        // Backend may still be building from profile hooks — keep polling.
      } finally {
        if (!cancelled) setGenerating(false);
      }
    };

    const poll = async () => {
      try {
        const next = await fetchCareerIntelligence();
        if (cancelled) return true;
        if (next) {
          setIntel(next);
          setAutoBuilding(false);
          return true;
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Couldn't load intelligence.",
          );
        }
      }
      return false;
    };

    void kickOffBuild();
    void poll();
    const id = window.setInterval(async () => {
      attempts += 1;
      const ready = await poll();
      if (ready || attempts >= 30) {
        window.clearInterval(id);
        if (!cancelled) {
          setAutoBuilding(false);
          if (!ready && attempts >= 30) {
            setError(
              "Aarya is still building your intelligence profile. Try Refresh in a moment.",
            );
          }
        }
      }
    }, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [loading, intel]);

  // Pick up background recomputes (resume upload, chat, etc.)
  useEffect(() => {
    if (!intel) return;
    const id = window.setInterval(async () => {
      try {
        const next = await fetchCareerIntelligence();
        if (!next) return;
        if (
          next.data_completeness !== intel.data_completeness ||
          next.career_dna?.primary_archetype !== intel.career_dna?.primary_archetype
        ) {
          setIntel(next);
        }
      } catch {
        // best-effort
      }
    }, 30_000);
    return () => window.clearInterval(id);
  }, [intel]);

  async function regenerate() {
    setGenerating(true);
    setError("");
    try {
      const data = await generateCareerIntelligence();
      setIntel(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Couldn't generate intelligence. Try again shortly.",
      );
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <IntelSkeleton />;

  if (!intel || isPlaceholderIntelligence(intel)) {
    return (
      <Card>
        <CardBody>
          <div className="flex flex-col items-center gap-4 py-6 text-center">
            <div className="w-14 h-14 rounded-2xl bg-ink-100 flex items-center justify-center">
              {autoBuilding || generating ? (
                <Loader2
                  className="h-7 w-7 text-accent animate-spin"
                  strokeWidth={1.5}
                />
              ) : (
                <Brain className="h-7 w-7 text-ink-500" strokeWidth={1.5} />
              )}
            </div>
            <div className="space-y-1">
              <p className="text-small font-semibold text-ink-900">
                {autoBuilding || generating
                  ? "Building your career intelligence…"
                  : "Your intelligence profile is on the way"}
              </p>
              <p className="text-micro text-ink-500 max-w-sm">
                Aarya builds a 24-layer profile from your resume, chats, and
                sign-in details — archetype, trajectory, market value, mobility,
                predictions and more. This updates automatically as you share
                more.
              </p>
            </div>
            {!autoBuilding && !generating && error && (
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />}
                onClick={() => void regenerate()}
              >
                Try again
              </Button>
            )}
            {error && (
              <p className="text-small text-destructive text-center">{error}</p>
            )}
          </div>
        </CardBody>
      </Card>
    );
  }

  const i = intel;
  const salaryOpts = { market };

  // ── Hero headline values ───────────────────────────────────────────────────
  const primaryArchetype = i.career_dna?.primary_archetype;
  const secondaryArchetype = i.career_dna?.secondary_archetype;
  const completeness =
    i.data_completeness !== null && i.data_completeness !== undefined
      ? Math.min(100, Math.round(i.data_completeness))
      : null;
  const marketValue = formatCompensationAmount(
    i.compensation?.current_market_value,
    salaryOpts,
  );
  const nextRole = i.prediction?.most_likely_next_role?.outcome;
  const nextRoleConf = pct(i.prediction?.most_likely_next_role?.confidence);
  const momentum =
    i.trajectory?.career_momentum_score !== null &&
    i.trajectory?.career_momentum_score !== undefined
      ? `${i.trajectory.career_momentum_score}/100`
      : null;
  const totalYears =
    i.experience?.total_years !== null && i.experience?.total_years !== undefined
      ? `${i.experience.total_years} yrs`
      : null;

  // ── Which groups have any content (skip empty ones) ─────────────────────────
  const hasWho = !!(
    hasScoreMap(i.career_dna?.archetype_scores) ||
    i.identity?.personal_profile?.current_location ||
    i.identity?.career_preferences?.work_mode ||
    (i.experience?.role_history && i.experience.role_history.length > 0) ||
    i.experience?.total_years ||
    (i.skills?.hard_skills && i.skills.hard_skills.length > 0) ||
    (i.skills?.soft_skills && i.skills.soft_skills.length > 0) ||
    (i.behavioral?.working_style && i.behavioral.working_style.length > 0)
  );
  const hasStanding = !!(
    hasMeaningfulFacts(i.achievements as Record<string, unknown> | undefined) ||
    i.leadership?.leadership_stage ||
    i.leadership?.executive_readiness_score ||
    (i.leadership?.signals && i.leadership.signals.length > 0) ||
    i.trajectory?.career_momentum_score ||
    (i.trajectory?.growth_path && i.trajectory.growth_path.length > 0) ||
    (i.learning?.certifications && i.learning.certifications.length > 0) ||
    (i.industry?.industry_exposure && i.industry.industry_exposure.length > 0) ||
    hasScoreMap(i.functional?.scores) ||
    i.brand?.headline_quality ||
    i.network?.connections ||
    hasScoreMap(i.market as Record<string, number | null> | undefined) ||
    i.compensation?.current_market_value ||
    i.employability?.employability_score
  );
  const hasFuture = !!(
    (i.mobility?.adjacent_roles && i.mobility.adjacent_roles.length > 0) ||
    (i.mobility?.stretch_roles && i.mobility.stretch_roles.length > 0) ||
    (i.mobility?.pivot_roles && i.mobility.pivot_roles.length > 0) ||
    i.goals?.explicit_goals?.desired_title ||
    i.prediction?.most_likely_next_role?.outcome ||
    (i.path_graph?.conservative_path && i.path_graph.conservative_path.length > 0) ||
    (i.recommendations?.jobs && i.recommendations.jobs.length > 0)
  );
  const hasGaps = !!(
    (i.gap_analysis && i.gap_analysis.length > 0) ||
    i.risk?.job_hopping_risk ||
    i.hidden_signals?.ambition_score ||
    (i.open_questions && i.open_questions.length > 0)
  );

  return (
    <div className="space-y-4">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <Card>
        <CardBody className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              {primaryArchetype && (
                <Badge tone="strong">{primaryArchetype}</Badge>
              )}
              {secondaryArchetype && <Badge>{secondaryArchetype}</Badge>}
              {completeness !== null && (
                <Badge tone="accent">{completeness}% complete</Badge>
              )}
            </div>
            <Button
              variant="secondary"
              size="sm"
              loading={generating}
              leftIcon={
                <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
              }
              onClick={() => void regenerate()}
              className="shrink-0"
            >
              {generating ? "Refreshing…" : "Refresh"}
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Stat label="Market value" value={marketValue} />
            <Stat
              label="Likely next role"
              value={
                nextRole
                  ? nextRoleConf
                    ? `${nextRole} · ${nextRoleConf}`
                    : nextRole
                  : null
              }
            />
            <Stat label="Career momentum" value={momentum} />
            <Stat label="Experience" value={totalYears} />
          </div>

          {onAskAarya && (nextRole || marketValue || hasGaps) && (
            <div className="flex flex-wrap gap-2">
              {nextRole && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() =>
                    onAskAarya(
                      `Find me current jobs matching the "${nextRole}" direction in my market, strongest fit first.`,
                    )
                  }
                >
                  See matching roles
                </Button>
              )}
              {marketValue && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    onAskAarya(
                      `Based on my market value of ${marketValue}, find me roles that pay in that range.`,
                    )
                  }
                >
                  Roles at my market value
                </Button>
              )}
              {hasGaps && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    onAskAarya(
                      "Based on my career intelligence, what are my biggest gaps and a concrete plan to close them?",
                    )
                  }
                >
                  Plan my gaps
                </Button>
              )}
            </div>
          )}

          {i.career_dna?.rationale && (
            <p className="text-small text-ink-600 leading-relaxed">
              {i.career_dna.rationale}
            </p>
          )}

          {i.updated_at && (
            <p className="text-micro text-ink-400">
              Updated {new Date(i.updated_at).toLocaleDateString("en-IN")}
            </p>
          )}
        </CardBody>
      </Card>

      {error && <p className="text-small text-destructive">{error}</p>}

      {/* ── Group 1: Who you are ──────────────────────────────────────────── */}
      {hasWho && (
        <CollapsibleGroup title="Who you are" defaultOpen>
          {/* Career DNA */}
          {i.career_dna?.archetype_scores && hasScoreMap(i.career_dna.archetype_scores) && (
            <Layer title="Career DNA">
              <ScoreGrid scores={i.career_dna.archetype_scores} />
            </Layer>
          )}

          {/* Identity */}
          {i.identity && (
            <Layer title="Identity">
              {i.identity.personal_profile && (
                <div>
                  <Fact
                    label="location"
                    value={i.identity.personal_profile.current_location}
                  />
                  <Fact
                    label="work authorization"
                    value={i.identity.personal_profile.work_authorization}
                  />
                  <Fact
                    label="visa status"
                    value={i.identity.personal_profile.visa_status}
                  />
                  <Fact
                    label="relocation"
                    value={i.identity.personal_profile.relocation_preferences}
                  />
                  <Fact
                    label="timezone"
                    value={i.identity.personal_profile.timezone}
                  />
                  {i.identity.personal_profile.languages &&
                    i.identity.personal_profile.languages.length > 0 && (
                      <div className="pt-2">
                        <Chips items={i.identity.personal_profile.languages} />
                      </div>
                    )}
                </div>
              )}
              {i.identity.career_preferences && (
                <div className="pt-1">
                  <Fact
                    label="work mode"
                    value={i.identity.career_preferences.work_mode}
                  />
                  <Fact
                    label="travel"
                    value={i.identity.career_preferences.travel_willingness}
                  />
                  <Fact
                    label="company size"
                    value={
                      i.identity.career_preferences.company_size_preference
                    }
                  />
                  <Fact
                    label="startup vs enterprise"
                    value={
                      i.identity.career_preferences.startup_vs_enterprise
                    }
                  />
                  {i.identity.career_preferences.industry_preference &&
                    i.identity.career_preferences.industry_preference.length >
                      0 && (
                      <div className="pt-2">
                        <Chips
                          items={
                            i.identity.career_preferences.industry_preference
                          }
                        />
                      </div>
                    )}
                </div>
              )}
            </Layer>
          )}

          {/* Experience */}
          {i.experience && (
            <Layer title="Experience">
              <Fact
                label="total years"
                value={i.experience.total_years ?? undefined}
              />
              {i.experience.role_history &&
                i.experience.role_history.length > 0 && (
                  <div className="space-y-2 pt-1">
                    {i.experience.role_history.map((r, idx) => (
                      <div
                        key={`${r.title}-${idx}`}
                        className="rounded-md border border-ink-100 px-3 py-2"
                      >
                        <p className="text-small font-medium text-ink-900">
                          {r.title ?? "—"}
                        </p>
                        <p className="text-micro text-ink-500">
                          {[r.function, r.industry, r.seniority]
                            .filter(Boolean)
                            .join(" · ") || "—"}
                        </p>
                        <p className="text-micro text-ink-400">
                          {[
                            r.duration_months
                              ? `${r.duration_months} mo`
                              : null,
                            r.team_size ? `team of ${r.team_size}` : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                        {r.aarya_insights && r.aarya_insights.length > 0 && (
                          <ul className="mt-2 list-disc pl-4 space-y-0.5">
                            {r.aarya_insights.map((line, iidx) => (
                              <li
                                key={iidx}
                                className="text-micro text-ink-600 leading-snug"
                              >
                                {line}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              <ScoreGrid scores={i.experience.experience_vector as never} />
            </Layer>
          )}

          {/* Skills */}
          {i.skills && (
            <Layer title="Skills">
              {i.skills.hard_skills && i.skills.hard_skills.length > 0 && (
                <div className="space-y-2">
                  <p className="text-micro text-ink-400">Hard skills</p>
                  <HardSkillList items={i.skills.hard_skills} />
                </div>
              )}
              {i.skills.soft_skills && i.skills.soft_skills.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-micro text-ink-400">Soft skills</p>
                  <Chips items={i.skills.soft_skills} />
                </div>
              )}
              {i.skills.future_skills && i.skills.future_skills.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-micro text-ink-400">Skills to grow into</p>
                  <Chips items={i.skills.future_skills} />
                </div>
              )}
            </Layer>
          )}

          {/* Behavioral */}
          {i.behavioral && (
            <Layer title="Working style">
              {i.behavioral.working_style &&
                i.behavioral.working_style.length > 0 && (
                  <Chips items={i.behavioral.working_style} />
                )}
              {i.behavioral.decision_style &&
                i.behavioral.decision_style.length > 0 && (
                  <Chips items={i.behavioral.decision_style} />
                )}
              <Fact label="risk appetite" value={i.behavioral.risk_appetite} />
            </Layer>
          )}
        </CollapsibleGroup>
      )}

      {/* ── Group 2: Strengths & standing ─────────────────────────────────── */}
      {hasStanding && (
        <CollapsibleGroup title="Strengths & standing">
          {i.achievements && hasMeaningfulFacts(i.achievements as Record<string, unknown>) && (
            <Layer title="Achievements">
              <div>
                {Object.entries(i.achievements).map(([k, v]) => {
                  if (v == null || v === "") return null;
                  if (Array.isArray(v) && v.length === 0) return null;
                  return (
                    <Fact
                      key={k}
                      label={k}
                      value={Array.isArray(v) ? v.join(", ") : v}
                    />
                  );
                })}
              </div>
            </Layer>
          )}

          {i.leadership && (
            <Layer title="Leadership">
              <Fact label="stage" value={i.leadership.leadership_stage} />
              <ScoreBar
                label="executive readiness"
                value={i.leadership.executive_readiness_score}
              />
              {i.leadership.signals && i.leadership.signals.length > 0 && (
                <Chips items={i.leadership.signals} />
              )}
            </Layer>
          )}

          {i.trajectory && (
            <Layer title="Trajectory">
              <Fact
                label="promotion velocity"
                value={
                  i.trajectory.promotion_velocity_months
                    ? `${i.trajectory.promotion_velocity_months} mo / level`
                    : undefined
                }
              />
              <ScoreBar
                label="career momentum"
                value={i.trajectory.career_momentum_score}
              />
              {i.trajectory.growth_path &&
                i.trajectory.growth_path.length > 0 && (
                  <Chips items={i.trajectory.growth_path} />
                )}
            </Layer>
          )}

          {i.learning && (
            <Layer title="Learning">
              <ScoreBar
                label="learning velocity"
                value={i.learning.learning_velocity}
              />
              {i.learning.certifications &&
                i.learning.certifications.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-micro text-ink-400">Certifications</p>
                    <Chips items={i.learning.certifications} />
                  </div>
                )}
              {i.learning.courses && i.learning.courses.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-micro text-ink-400">Courses</p>
                  <Chips items={i.learning.courses} />
                </div>
              )}
            </Layer>
          )}

          {i.industry && (
            <Layer title="Industry">
              <ScoreBar
                label="transferability"
                value={i.industry.transferability_score}
              />
              {i.industry.industry_exposure &&
                i.industry.industry_exposure.length > 0 && (
                  <Chips items={i.industry.industry_exposure} />
                )}
              <ScoreGrid scores={i.industry.industry_depth} />
            </Layer>
          )}

          {i.functional?.scores &&
            Object.keys(i.functional.scores).length > 0 && (
              <Layer title="Functional strengths">
                <ScoreGrid scores={i.functional.scores} />
              </Layer>
            )}

          {i.brand && Object.keys(i.brand).length > 0 && (
            <Layer title="Professional brand">
              <div>
                {Object.entries(i.brand).map(([k, v]) =>
                  typeof v === "number" ? (
                    <ScoreBar key={k} label={k} value={v} />
                  ) : (
                    <Fact key={k} label={k} value={v} />
                  ),
                )}
              </div>
            </Layer>
          )}

          {i.network && Object.keys(i.network).length > 0 && (
            <Layer title="Network">
              <ScoreGrid scores={i.network as never} />
            </Layer>
          )}

          {i.market && Object.keys(i.market).length > 0 && (
            <Layer title="Market position">
              <ScoreGrid scores={i.market as never} />
            </Layer>
          )}

          {i.compensation && (
            <Layer title="Compensation">
              <Fact
                label="current market value"
                value={formatCompensationAmount(
                  i.compensation.current_market_value,
                  salaryOpts,
                )}
              />
              {i.compensation.salary_range &&
                (i.compensation.salary_range.min ||
                  i.compensation.salary_range.max) && (
                  <Fact
                    label="salary range"
                    value={
                      formatSalaryRange(
                        i.compensation.salary_range.min,
                        i.compensation.salary_range.max,
                        salaryOpts,
                      ) ?? "—"
                    }
                  />
                )}
              <Fact
                label="total compensation"
                value={formatCompensationAmount(
                  i.compensation.total_compensation,
                  salaryOpts,
                )}
              />
              <Fact label="equity" value={i.compensation.equity_potential} />
              <ScoreBar
                label="comp growth potential"
                value={i.compensation.compensation_growth_potential}
              />
            </Layer>
          )}

          {i.employability && Object.keys(i.employability).length > 0 && (
            <Layer title="Employability">
              <ScoreGrid scores={i.employability as never} />
            </Layer>
          )}
        </CollapsibleGroup>
      )}

      {/* ── Group 3: Where you're going ───────────────────────────────────── */}
      {hasFuture && (
        <CollapsibleGroup title="Where you're going">
          {i.mobility &&
            (i.mobility.adjacent_roles?.length ||
              i.mobility.stretch_roles?.length ||
              i.mobility.pivot_roles?.length) && (
              <Layer title="Mobility">
                {i.mobility.adjacent_roles &&
                  i.mobility.adjacent_roles.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-micro text-ink-400">Adjacent roles</p>
                      <MobilityList items={i.mobility.adjacent_roles} onAskAarya={onAskAarya} />
                    </div>
                  )}
                {i.mobility.stretch_roles &&
                  i.mobility.stretch_roles.length > 0 && (
                    <div className="space-y-2 pt-1">
                      <p className="text-micro text-ink-400">Stretch roles</p>
                      <MobilityList items={i.mobility.stretch_roles} onAskAarya={onAskAarya} />
                    </div>
                  )}
                {i.mobility.pivot_roles &&
                  i.mobility.pivot_roles.length > 0 && (
                    <div className="space-y-2 pt-1">
                      <p className="text-micro text-ink-400">Pivot roles</p>
                      <MobilityList items={i.mobility.pivot_roles} onAskAarya={onAskAarya} />
                    </div>
                  )}
              </Layer>
            )}

          {i.goals && (
            <Layer title="Goals">
              {i.goals.explicit_goals && (
                <div>
                  <Fact
                    label="desired title"
                    value={i.goals.explicit_goals.desired_title}
                  />
                  <Fact
                    label="desired industry"
                    value={i.goals.explicit_goals.desired_industry}
                  />
                  <Fact
                    label="desired salary"
                    value={formatCompensationAmount(
                      i.goals.explicit_goals.desired_salary,
                      salaryOpts,
                    )}
                  />
                </div>
              )}
              {i.goals.inferred_goals &&
                i.goals.inferred_goals.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-micro text-ink-400">Inferred goals</p>
                    <Chips items={i.goals.inferred_goals} />
                  </div>
                )}
            </Layer>
          )}

          {i.prediction && (
            <Layer title="AI predictions">
              <div>
                <PredictionRow
                  label="Most likely next role"
                  pred={i.prediction.most_likely_next_role}
                />
                <PredictionRow
                  label="Most likely promotion"
                  pred={i.prediction.most_likely_promotion}
                />
                <PredictionRow
                  label="3-year outlook"
                  pred={i.prediction.outcome_3_year}
                />
                <PredictionRow
                  label="5-year outlook"
                  pred={i.prediction.outcome_5_year}
                />
                <PredictionRow
                  label="10-year outlook"
                  pred={i.prediction.outcome_10_year}
                />
              </div>
            </Layer>
          )}

          {i.path_graph &&
            (i.path_graph.conservative_path?.length ||
              i.path_graph.accelerated_path?.length ||
              i.path_graph.pivot_path?.length ||
              i.path_graph.entrepreneur_path?.length) && (
              <Layer title="Career paths">
                {(
                  [
                    ["Conservative", i.path_graph.conservative_path],
                    ["Accelerated", i.path_graph.accelerated_path],
                    ["Pivot", i.path_graph.pivot_path],
                    ["Entrepreneur", i.path_graph.entrepreneur_path],
                  ] as const
                ).map(([label, steps]) =>
                  steps && steps.length > 0 ? (
                    <div key={label} className="space-y-1.5">
                      <p className="text-micro text-ink-400">{label}</p>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {steps.map((step, idx) => (
                          <span
                            key={`${step}-${idx}`}
                            className="inline-flex items-center gap-1.5"
                          >
                            <Badge>{step}</Badge>
                            {idx < steps.length - 1 && (
                              <span className="text-ink-300">→</span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null,
                )}
              </Layer>
            )}

          {i.recommendations &&
            Object.keys(i.recommendations).length > 0 && (
              <Layer title="Recommendations">
                <div className="space-y-3">
                  {Object.entries(i.recommendations).map(([k, list]) =>
                    Array.isArray(list) && list.length > 0 ? (
                      <div key={k} className="space-y-1.5">
                        <p className="text-micro text-ink-400 capitalize">
                          {k.replace(/_/g, " ")}
                        </p>
                        <ul className="space-y-1">
                          {list.map((item, idx) => (
                            <li
                              key={`${item}-${idx}`}
                              className="text-small text-ink-700 flex gap-2"
                            >
                              <span className="text-ink-300">•</span>
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null,
                  )}
                </div>
              </Layer>
            )}
        </CollapsibleGroup>
      )}

      {/* ── Group 4: Gaps & risks ─────────────────────────────────────────── */}
      {hasGaps && (
        <CollapsibleGroup title="Gaps & risks">
          {i.gap_analysis && i.gap_analysis.length > 0 && (
            <Layer title="Gap analysis">
              <div className="space-y-3">
                {i.gap_analysis.map((g, idx) => (
                  <div
                    key={`${g.target_role}-${idx}`}
                    className="rounded-md border border-ink-100 px-3 py-2 space-y-2"
                  >
                    <p className="text-small font-medium text-ink-900">
                      {g.target_role}
                    </p>
                    {g.missing_skills && g.missing_skills.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-micro text-ink-400">Missing skills</p>
                        <Chips items={g.missing_skills} />
                      </div>
                    )}
                    {g.missing_experience &&
                      g.missing_experience.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-micro text-ink-400">
                            Missing experience
                          </p>
                          <Chips items={g.missing_experience} />
                        </div>
                      )}
                    {g.missing_certifications &&
                      g.missing_certifications.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-micro text-ink-400">
                            Missing certifications
                          </p>
                          <Chips items={g.missing_certifications} />
                        </div>
                      )}
                    {g.missing_leadership_signals &&
                      g.missing_leadership_signals.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-micro text-ink-400">
                            Missing leadership signals
                          </p>
                          <Chips items={g.missing_leadership_signals} />
                        </div>
                      )}
                    {g.missing_industry_exposure &&
                      g.missing_industry_exposure.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-micro text-ink-400">
                            Missing industry exposure
                          </p>
                          <Chips items={g.missing_industry_exposure} />
                        </div>
                      )}
                  </div>
                ))}
              </div>
            </Layer>
          )}

          {i.risk && Object.keys(i.risk).length > 0 && (
            <Layer title="Risk factors">
              <div>
                {Object.entries(i.risk).map(([k, v]) =>
                  typeof v === "number" ? (
                    <ScoreBar key={k} label={k} value={v} />
                  ) : (
                    <Fact key={k} label={k} value={v} />
                  ),
                )}
              </div>
            </Layer>
          )}

          {i.hidden_signals && Object.keys(i.hidden_signals).length > 0 && (
            <Layer title="Hidden signals">
              <ScoreGrid scores={i.hidden_signals as never} />
            </Layer>
          )}

          {i.open_questions && i.open_questions.length > 0 && (
            <Layer
              title="Help Aarya learn more"
              description="Answer these in chat and your intelligence sharpens automatically."
            >
              <ul className="space-y-1.5">
                {i.open_questions.map((q, idx) => (
                  <li
                    key={`${q}-${idx}`}
                    className="text-small text-ink-700 flex gap-2"
                  >
                    <span className="text-ink-300">{idx + 1}.</span>
                    {q}
                  </li>
                ))}
              </ul>
            </Layer>
          )}
        </CollapsibleGroup>
      )}

      {i.model && (
        <p className="text-micro text-ink-300 text-center pt-1">
          Generated by {i.model}
        </p>
      )}
    </div>
  );
}
