"use client";

/**
 * JobDetailView — full-page job detail (the new-tab target of a JobCard click).
 *
 * Mirrors the content of the old JobDetailDrawer (company/title/score, badges,
 * match breakdown, required skills, Aarya's take) but as a focused standalone
 * page so it can be deep-linked and opened in its own tab.
 *
 *   - Request intro → hops to the chat with a pre-filled message (intro creation
 *     is conversation-mediated via Aarya).
 *   - Apply → opens the employer's native apply URL.
 *   - Save → toggles the saved-jobs list.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  ExternalLink,
  Heart,
  Loader2,
  Send,
  Sparkles,
} from "@/components/brand/icons";
import { fetchSingleMatch, type MatchedJob } from "@/lib/api/matches";
import { fetchSavedJobIds, saveJob, unsaveJob } from "@/lib/api/saved-jobs";
import { cn } from "@/lib/utils";
import { formatSalaryRange } from "@/lib/salary";
import { AppShell } from "@/components/layout/AppShell";
import { Avatar, Badge, Button, ScoreDot, useToast } from "@/components/ui";

const SENIORITY_LABELS: Record<string, string> = {
  intern: "Intern",
  junior: "Junior",
  mid: "Mid-level",
  senior: "Senior",
  lead: "Lead",
  director: "Director",
  vp: "VP",
  c_level: "C-Level",
};

const EMP_LABELS: Record<string, string> = {
  full_time: "Full-time",
  contract: "Contract",
  internship: "Internship",
  part_time: "Part-time",
};

/**
 * Render a flat job-description string as structured rich text: lines ending in
 * ":" become section headings, short lines under them become bullet lists, and
 * long multi-sentence lines stay as paragraphs. Turns the raw ATS/LinkedIn blob
 * into something readable instead of one wall of text.
 */
function RichText({ text }: { text: string }) {
  type Block =
    | { type: "heading"; text: string }
    | { type: "para"; text: string }
    | { type: "list"; items: string[] };

  const blocks: Block[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  };

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (line.endsWith(":") && line.length <= 70) {
      flush();
      blocks.push({ type: "heading", text: line.replace(/:\s*$/, "") });
      continue;
    }
    const sentences = (line.match(/[.!?](\s|$)/g) ?? []).length;
    const isParagraph = line.length > 140 || sentences >= 2;
    if (isParagraph && list.length === 0) {
      blocks.push({ type: "para", text: line });
    } else {
      list.push(line.replace(/^[•\-*]\s*/, ""));
    }
  }
  flush();

  return (
    <div className="space-y-2">
      {blocks.map((b, i) =>
        b.type === "heading" ? (
          <p key={i} className="text-small font-semibold text-ink-900 pt-2">
            {b.text}
          </p>
        ) : b.type === "list" ? (
          <ul key={i} className="list-disc pl-5 space-y-1">
            {b.items.map((item, j) => (
              <li key={j} className="text-body text-ink-700 leading-relaxed">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <p key={i} className="text-body text-ink-700 leading-relaxed">
            {b.text}
          </p>
        )
      )}
    </div>
  );
}

/** "3 days ago" / "today" from an ISO date, or null if unparseable. */
function postedAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return "Posted today";
  if (days === 1) return "Posted yesterday";
  if (days < 30) return `Posted ${days} days ago`;
  const months = Math.floor(days / 30);
  return `Posted ${months} month${months > 1 ? "s" : ""} ago`;
}

type JobDetailViewProps = {
  jobId: string;
  userName?: string;
  userAvatarUrl?: string | null;
};

export function JobDetailView({
  jobId,
  userName,
  userAvatarUrl,
}: JobDetailViewProps) {
  const router = useRouter();
  const { toast } = useToast();

  const [job, setJob] = useState<MatchedJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [introSent, setIntroSent] = useState(false);
  const [prepStarted, setPrepStarted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSingleMatch(jobId)
      .then((data) => {
        if (cancelled) return;
        setJob(data);
        return fetchSavedJobIds().then((ids) => {
          if (!cancelled) setSaved(ids.has(jobId));
        });
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Couldn't load this job.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const handleRequestIntro = () => {
    if (!job) return;
    setIntroSent(true);
    const msg = `I'd like to request an intro for the "${job.title}" role at ${
      job.company_name ?? "this company"
    } (job ID: ${job.job_id}).`;
    router.push(`/dashboard?init=${encodeURIComponent(msg)}`);
  };

  // Assets-first flow: generate the full AI application kit (tailored resume,
  // cover letter, interview prep) BEFORE the intro, then tee up the warm intro
  // once the candidate is genuinely ready to be introduced.
  const handlePrepare = () => {
    if (!job) return;
    setPrepStarted(true);
    const msg =
      `Prepare my full application kit for the "${job.title}" role at ${
        job.company_name ?? "this company"
      } (job ID: ${job.job_id}) — a tailored resume, a cover letter, and interview prep. ` +
      `Once everything's ready, walk me through it and then help me request a warm intro.`;
    router.push(`/dashboard?init=${encodeURIComponent(msg)}`);
  };

  const handleApply = () => {
    if (job?.apply_url) {
      window.open(job.apply_url, "_blank", "noopener,noreferrer");
    }
  };

  const handleSaveToggle = async () => {
    if (!job || saving) return;
    setSaving(true);
    const next = !saved;
    try {
      if (next) {
        await saveJob(job.job_id);
        toast.success("Saved to Jobs");
      } else {
        await unsaveJob(job.job_id);
        toast.success("Removed from saved");
      }
      setSaved(next);
    } catch {
      toast.error(next ? "Couldn't save job" : "Couldn't remove saved job");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell
      title="Job details"
      width="form"
      activeNav="matches"
      userName={userName}
      userAvatarUrl={userAvatarUrl}
      action={
        <Link
          href="/dashboard?panel=jobs"
          className="inline-flex items-center gap-1.5 text-small text-ink-500 hover:text-ink-900 transition-colors duration-fast"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          Back to jobs
        </Link>
      }
    >
      {loading ? (
        <JobDetailSkeleton />
      ) : error || !job ? (
        <div className="rounded-xl border border-ink-100 bg-paper-1 px-6 py-12 text-center">
          <p className="text-body text-ink-700">
            {error ?? "This job couldn't be found."}
          </p>
          <Link
            href="/dashboard?panel=jobs"
            className="mt-4 inline-block text-small font-medium text-accent hover:underline"
          >
            ← Back to your matches
          </Link>
        </div>
      ) : (
        <JobDetailBody
          job={job}
          saved={saved}
          saving={saving}
          introSent={introSent}
          prepStarted={prepStarted}
          onPrepare={handlePrepare}
          onRequestIntro={handleRequestIntro}
          onApply={handleApply}
          onSaveToggle={() => void handleSaveToggle()}
        />
      )}
    </AppShell>
  );
}

// ── Body ──────────────────────────────────────────────────────────────────────

function JobDetailBody({
  job,
  saved,
  saving,
  introSent,
  prepStarted,
  onPrepare,
  onRequestIntro,
  onApply,
  onSaveToggle,
}: {
  job: MatchedJob;
  saved: boolean;
  saving: boolean;
  introSent: boolean;
  prepStarted: boolean;
  onPrepare: () => void;
  onRequestIntro: () => void;
  onApply: () => void;
  onSaveToggle: () => void;
}) {
  const ctcLabel = formatSalaryRange(job.ctc_min, job.ctc_max, {
    currency: job.salary_currency,
  });

  const locationLabel =
    [job.location_city, job.location_state].filter(Boolean).join(", ") ||
    (job.is_remote ? "Remote" : "Onsite");

  const posted = postedAgo(job.posted_at);
  // Split skills into "you have" vs "gap" when the API provides it; otherwise
  // fall back to the flat required list.
  const matched = job.skills_matched ?? [];
  const gaps = job.skills_gap ?? [];
  const hasSkillSplit = matched.length > 0 || gaps.length > 0;

  const breakdown: { label: string; value: number | null }[] = [
    { label: "Skills", value: job.skills_score },
    { label: "Experience", value: job.experience_score },
    { label: "Location", value: job.location_score },
    { label: "Compensation", value: job.ctc_score },
  ].filter((b) => b.value !== null);

  return (
    <div className="space-y-6">
      {/* Company + title + score */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <Avatar name={job.company_name ?? "?"} size="lg" tone="light" />
          <div className="min-w-0">
            <p className="text-small text-ink-500">
              {job.company_name ?? "Company"}
              <span className="text-ink-300"> · </span>
              {locationLabel}
              {posted && (
                <>
                  <span className="text-ink-300"> · </span>
                  {posted}
                </>
              )}
            </p>
            <h2 className="text-h1 text-ink-900 leading-tight mt-0.5">
              {job.title}
            </h2>
          </div>
        </div>
        <ScoreDot value={job.overall_score} size="lg" label="match" />
      </div>

      {/* Badges */}
      <div className="flex flex-wrap items-center gap-1.5">
        {job.seniority && (
          <Badge>{SENIORITY_LABELS[job.seniority] ?? job.seniority}</Badge>
        )}
        {job.employment_type && (
          <Badge>{EMP_LABELS[job.employment_type] ?? job.employment_type}</Badge>
        )}
        {job.is_remote && <Badge>Remote</Badge>}
        {ctcLabel && <Badge tone="accent">{ctcLabel}</Badge>}
      </div>

      {/* Match breakdown — lead with the qualitative tier, number secondary */}
      {breakdown.length > 0 && (
        <div className="space-y-2.5 rounded-xl border border-ink-100 bg-paper-1 p-4">
          <div className="flex items-baseline justify-between gap-2">
            <p className="text-small font-semibold text-ink-900">
              {job.tier_label ?? "How you fit"}
            </p>
            <span className="text-micro text-ink-400">
              {Math.round(job.overall_score * 100)}% overall
            </span>
          </div>
          <div className="space-y-2">
            {breakdown.map(({ label, value }) => {
              const pct = Math.round((value as number) * 100);
              return (
                <div key={label} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 text-small text-ink-600">
                    {label}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full bg-ink-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-ink-900"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="w-9 shrink-0 text-right text-micro font-medium text-ink-700">
                    {pct}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Aarya's take */}
      {job.explanation && (
        <div className="space-y-1.5">
          <p className="text-small font-semibold text-ink-900">
            Aarya&apos;s take
          </p>
          <p className="text-body text-ink-700 leading-relaxed">
            {job.explanation}
          </p>
        </div>
      )}

      {/* Skills — split into what you have vs gaps when available */}
      {hasSkillSplit ? (
        <div className="space-y-3">
          {matched.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-small font-semibold text-ink-900">
                Skills you have ({matched.length}/{job.skills_required.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {matched.map((skill) => (
                  <span
                    key={skill}
                    className="inline-flex items-center gap-1 text-small text-ink-900 bg-ink-100 px-2 py-0.5 rounded-sm"
                  >
                    <Check className="h-3 w-3" strokeWidth={2.5} />
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}
          {gaps.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-small font-semibold text-ink-900">
                Skill gaps ({gaps.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {gaps.map((skill) => (
                  <span
                    key={skill}
                    className="text-small text-ink-500 bg-paper-1 border border-dashed border-ink-200 px-2 py-0.5 rounded-sm"
                  >
                    {skill}
                  </span>
                ))}
              </div>
              <p className="text-micro text-ink-400">
                Ask Aarya how to close these — or whether they’re really needed.
              </p>
            </div>
          )}
        </div>
      ) : (
        job.skills_required.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-small font-semibold text-ink-900">
              Skills required
            </p>
            <div className="flex flex-wrap gap-1.5">
              {job.skills_required.map((skill) => (
                <span
                  key={skill}
                  className="text-small text-ink-600 bg-ink-50 px-2 py-0.5 rounded-sm"
                >
                  {skill}
                </span>
              ))}
            </div>
          </div>
        )
      )}

      {/* Full job description — read the whole posting without leaving the app */}
      {(job.description || job.requirements) && (
        <div className="space-y-1.5">
          <p className="text-small font-semibold text-ink-900">
            About this role
          </p>
          {job.description && <RichText text={job.description} />}
          {job.requirements && (
            <div className="pt-2">
              <p className="text-small font-medium text-ink-900 mb-1">Requirements</p>
              <RichText text={job.requirements} />
            </div>
          )}
        </div>
      )}

      {/* Actions — assets first (prepare the AI kit), then the warm intro. */}
      <div className="space-y-2 pt-4 border-t border-ink-100">
        <Button
          variant={prepStarted ? "secondary" : "primary"}
          size="md"
          onClick={onPrepare}
          disabled={prepStarted}
          leftIcon={
            prepStarted ? (
              <Check className="h-4 w-4" strokeWidth={2} />
            ) : (
              <Sparkles className="h-4 w-4" strokeWidth={1.5} />
            )
          }
          className="w-full"
        >
          {prepStarted ? "Opening chat…" : "Prepare application"}
        </Button>
        <p className="text-micro text-ink-400 text-center">
          Aarya tailors your resume, cover letter & interview prep — then sets up the intro.
        </p>

        <div className="flex items-center gap-2 pt-1">
          <Button
            variant="secondary"
            size="md"
            onClick={onRequestIntro}
            disabled={introSent}
            leftIcon={
              introSent ? (
                <Check className="h-4 w-4" strokeWidth={2} />
              ) : (
                <Send className="h-4 w-4" strokeWidth={1.5} />
              )
            }
            className="flex-1"
          >
            {introSent ? "Opening chat…" : "Request intro"}
          </Button>

          <Button
            variant="secondary"
            size="md"
            onClick={onApply}
            disabled={!job.apply_url}
            leftIcon={<ExternalLink className="h-4 w-4" strokeWidth={1.5} />}
            className="flex-1"
          >
            Apply
          </Button>

          <Button
            variant="ghost"
            size="md"
            onClick={onSaveToggle}
            disabled={saving}
            aria-label={saved ? "Remove from saved" : "Save job"}
            aria-pressed={saved}
            title={saved ? "Saved" : "Save job"}
            className={cn("shrink-0 px-3", saved && "text-accent")}
            leftIcon={
              saving ? (
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
              ) : (
                <Heart
                  className="h-4 w-4"
                  strokeWidth={1.5}
                  fill={saved ? "currentColor" : "none"}
                />
              )
            }
          />
        </div>
      </div>
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function JobDetailSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-xl bg-ink-100" />
        <div className="space-y-2">
          <div className="h-3 w-40 rounded bg-ink-100" />
          <div className="h-5 w-64 rounded bg-ink-100" />
        </div>
      </div>
      <div className="flex gap-1.5">
        <div className="h-6 w-20 rounded bg-ink-100" />
        <div className="h-6 w-20 rounded bg-ink-100" />
        <div className="h-6 w-16 rounded bg-ink-100" />
      </div>
      <div className="h-32 rounded-xl bg-ink-100" />
      <div className="h-20 rounded bg-ink-100" />
    </div>
  );
}
