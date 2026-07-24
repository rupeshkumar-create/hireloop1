"use client";

import { cn } from "@/lib/utils";
import { BTN_GHOST, BTN_PRIMARY } from "@/lib/button-classes";

export type ResumeAnalysis = {
  kind?: string;
  resume_id?: string | null;
  profile?: {
    full_name?: string | null;
    current_title?: string | null;
    current_company?: string | null;
    years_experience?: number | null;
    skills?: string[];
    notice_period_days?: number | null;
    expected_ctc_min_lpa?: number | null;
    expected_ctc_max_lpa?: number | null;
    current_ctc_lpa?: number | null;
    location_city?: string | null;
    location_state?: string | null;
  };
  gaps?: string[];
  strengths?: string[];
  weak_spots?: string[];
  version_compare?: {
    skills_added?: string[];
    skills_removed?: string[];
    what_improved?: string[];
  } | null;
  suggested_actions?: Array<{ id: string; label: string }>;
};

type Props = {
  analysis: ResumeAnalysis;
  onAction?: (actionId: string) => void;
};

export function ResumeAnalysisCard({ analysis, onAction }: Props) {
  const p = analysis.profile ?? {};
  const ctc =
    p.expected_ctc_min_lpa != null || p.expected_ctc_max_lpa != null
      ? `${p.expected_ctc_min_lpa ?? "?"}-${p.expected_ctc_max_lpa ?? "?"} LPA`
      : p.current_ctc_lpa != null
        ? `${p.current_ctc_lpa} LPA (current)`
        : "—";

  return (
    <div className="mt-3 rounded-xl border border-ink-100 bg-paper-1 p-4 space-y-3">
      <div>
        <p className="text-micro font-medium uppercase tracking-wide text-ink-500">
          Resume analysis
        </p>
        <h3 className="text-small font-semibold text-ink-900 mt-0.5">
          {p.current_title || "Profile from CV"}
          {p.current_company ? (
            <span className="font-normal text-ink-600"> · {p.current_company}</span>
          ) : null}
        </h3>
        <p className="text-micro text-ink-600 mt-1">
          {[
            p.years_experience != null ? `${p.years_experience}y exp` : null,
            p.location_city,
            ctc !== "—" ? ctc : null,
            p.notice_period_days != null ? `${p.notice_period_days}d notice` : null,
          ]
            .filter(Boolean)
            .join(" · ") || "Upload complete — review gaps below"}
        </p>
      </div>

      {p.skills && p.skills.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {p.skills.slice(0, 12).map((s) => (
            <span
              key={s}
              className="rounded-md bg-paper-0 px-2 py-0.5 text-micro text-ink-700 border border-ink-100"
            >
              {s}
            </span>
          ))}
        </div>
      ) : null}

      {analysis.gaps && analysis.gaps.length > 0 ? (
        <Section title="Gap checklist" items={analysis.gaps} tone="warn" />
      ) : null}
      {analysis.strengths && analysis.strengths.length > 0 ? (
        <Section title="Strengths" items={analysis.strengths} tone="good" />
      ) : null}
      {analysis.weak_spots && analysis.weak_spots.length > 0 ? (
        <Section title="Weak spots" items={analysis.weak_spots} tone="muted" />
      ) : null}

      {analysis.version_compare?.what_improved?.length ? (
        <Section
          title="What improved vs last CV"
          items={analysis.version_compare.what_improved}
          tone="good"
        />
      ) : null}

      {analysis.suggested_actions && onAction ? (
        <div className="flex flex-wrap gap-2 pt-1">
          {analysis.suggested_actions.map((a) => (
            <button
              key={a.id}
              type="button"
              className={cn(BTN_PRIMARY, "text-micro !py-1.5 !px-3")}
              onClick={() => onAction(a.id)}
            >
              {a.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Section({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "good" | "warn" | "muted";
}) {
  const color =
    tone === "good"
      ? "text-emerald-800"
      : tone === "warn"
        ? "text-amber-800"
        : "text-ink-700";
  return (
    <div>
      <p className={cn("text-micro font-medium", color)}>{title}</p>
      <ul className="mt-1 space-y-0.5">
        {items.map((item) => (
          <li key={item} className="text-micro text-ink-700 pl-3 relative before:content-['•'] before:absolute before:left-0">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export type JdFitAnalysis = {
  kind?: string;
  job_id?: string | null;
  overall_score?: number;
  section_scores?: Record<string, number>;
  section_notes?: Record<string, string>;
  must_haves?: { matched?: string[]; missing?: string[] };
  nice_to_haves?: { matched?: string[]; missing?: string[] };
  missing_keywords?: string[];
  should_apply?: { recommendation?: string; reason?: string };
  tailored_bullets?: string[];
  cover_letter_draft?: string;
  mock_interview_questions?: string[];
  salary_reality_check?: {
    suggested_min_lpa?: number;
    suggested_max_lpa?: number;
    note?: string;
  };
  suggested_actions?: Array<{
    id: string;
    label: string;
    requires_job_id?: boolean;
  }>;
  role?: { title?: string | null };
  candidate?: { full_name?: string | null; current_title?: string | null };
  bias_safe_checklist?: string[];
  filename?: string;
};

type FitProps = {
  analysis: JdFitAnalysis;
  onAction?: (actionId: string) => void;
};

export function JdFitAnalysisCard({ analysis, onAction }: FitProps) {
  const score = analysis.overall_score ?? 0;
  const rec = analysis.should_apply?.recommendation ?? "maybe";
  const sections = analysis.section_scores ?? {};

  return (
    <div className="mt-3 rounded-xl border border-ink-100 bg-paper-1 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-micro font-medium uppercase tracking-wide text-ink-500">
            {analysis.kind === "role_resume_analysis"
              ? "Resume vs live role"
              : "JD ↔ CV fit"}
          </p>
          <h3 className="text-small font-semibold text-ink-900 mt-0.5">
            {analysis.role?.title ||
              analysis.candidate?.current_title ||
              "Fit analysis"}
          </h3>
          {analysis.should_apply?.reason ? (
            <p className="text-micro text-ink-600 mt-1">{analysis.should_apply.reason}</p>
          ) : null}
        </div>
        <div className="text-right shrink-0">
          <p className="text-2xl font-semibold text-ink-900 tabular-nums">{score}%</p>
          <p className="text-micro capitalize text-ink-500">{rec}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Object.entries(sections).map(([k, v]) => (
          <div key={k} className="rounded-lg border border-ink-100 bg-paper-0 px-2 py-1.5">
            <p className="text-micro capitalize text-ink-500">{k}</p>
            <p className="text-small font-medium text-ink-900 tabular-nums">{v}%</p>
          </div>
        ))}
      </div>

      <TwoCol
        leftTitle="Must-haves matched"
        left={analysis.must_haves?.matched}
        rightTitle="Missing must-haves"
        right={analysis.must_haves?.missing}
      />
      <TwoCol
        leftTitle="Nice-to-haves matched"
        left={analysis.nice_to_haves?.matched}
        rightTitle="Nice-to-haves missing"
        right={analysis.nice_to_haves?.missing}
      />

      {analysis.salary_reality_check ? (
        <p className="text-micro text-ink-700">
          India salary band:{" "}
          <span className="font-medium">
            {analysis.salary_reality_check.suggested_min_lpa}–
            {analysis.salary_reality_check.suggested_max_lpa} LPA
          </span>
          {analysis.salary_reality_check.note
            ? ` — ${analysis.salary_reality_check.note}`
            : null}
        </p>
      ) : null}

      {analysis.tailored_bullets?.length ? (
        <Section title="Tailored bullets" items={analysis.tailored_bullets} tone="muted" />
      ) : null}

      {analysis.cover_letter_draft ? (
        <details className="text-micro">
          <summary className="cursor-pointer font-medium text-ink-800">
            Cover letter draft
          </summary>
          <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-paper-0 border border-ink-100 p-3 text-ink-700 font-sans">
            {analysis.cover_letter_draft}
          </pre>
        </details>
      ) : null}

      {analysis.mock_interview_questions?.length ? (
        <details className="text-micro">
          <summary className="cursor-pointer font-medium text-ink-800">
            Mock interview ({analysis.mock_interview_questions.length} questions)
          </summary>
          <ol className="mt-2 list-decimal pl-4 space-y-1 text-ink-700">
            {analysis.mock_interview_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ol>
        </details>
      ) : null}

      {analysis.bias_safe_checklist?.length ? (
        <Section
          title="Bias-safe screening checklist"
          items={analysis.bias_safe_checklist}
          tone="good"
        />
      ) : null}

      {analysis.suggested_actions && onAction ? (
        <div className="flex flex-wrap gap-2 pt-1">
          {analysis.suggested_actions.map((a) => {
            const needsJob = a.requires_job_id && !analysis.job_id;
            return (
              <button
                key={a.id}
                type="button"
                disabled={needsJob}
                title={needsJob ? "Save/find this role in catalog first" : undefined}
                className={cn(
                  needsJob ? BTN_GHOST : BTN_PRIMARY,
                  "text-micro !py-1.5 !px-3 disabled:opacity-40",
                )}
                onClick={() => onAction(a.id)}
              >
                {a.label}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function TwoCol({
  leftTitle,
  left,
  rightTitle,
  right,
}: {
  leftTitle: string;
  left?: string[];
  rightTitle: string;
  right?: string[];
}) {
  if (!left?.length && !right?.length) return null;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <MiniList title={leftTitle} items={left} />
      <MiniList title={rightTitle} items={right} />
    </div>
  );
}

function MiniList({ title, items }: { title: string; items?: string[] }) {
  return (
    <div className="rounded-lg border border-ink-100 bg-paper-0 p-2">
      <p className="text-micro font-medium text-ink-600">{title}</p>
      {items?.length ? (
        <ul className="mt-1 space-y-0.5">
          {items.slice(0, 8).map((i) => (
            <li key={i} className="text-micro text-ink-800">
              {i}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-micro text-ink-400 mt-1">None detected</p>
      )}
    </div>
  );
}
