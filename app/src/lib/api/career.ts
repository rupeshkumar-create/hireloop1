/**
 * Career-path API client — wraps the FastAPI /api/v1/career endpoints.
 *
 *   GET  /api/v1/career/path            → latest path (or null)
 *   POST /api/v1/career/path/generate   → (re)generate the path from the profile
 *   POST /api/v1/career/path/find-jobs  → jobs along the path + background top-up
 *
 * All calls go through the FastAPI backend (never direct Supabase from frontend).
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  parseReadyOrAccepted,
  type ReadyOrAccepted,
} from "@/lib/api/aiOperations";
import type { MatchedJob } from "@/lib/api/matches";

// ── Types ─────────────────────────────────────────────────────────────────────

export type CareerLevel = "current" | "next" | "future";

export type CareerStep = {
  title: string;
  level: CareerLevel | string;
  timeframe: string | null;
  rationale: string | null;
  skills_to_build: string[];
};

export type CareerPath = {
  id: string;
  current_role: string | null;
  summary: string | null;
  steps: CareerStep[];
  target_titles: string[];
  target_locations: string[];
  model: string | null;
  prioritized_title?: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type CareerPathResponse = {
  path: CareerPath | null;
};

export type FindJobsResult = {
  jobs: MatchedJob[];
  refreshing: boolean;
  target_titles: string[];
  /**
   * False only when zero jobs came back AND the upstream job source (Apify) is
   * unreachable — e.g. a missing/expired token. Lets the UI distinguish
   * "search is unavailable" from "no matches right now". Defaults to true.
   */
  source_available?: boolean;
};

export type CareerPathResume = {
  id: string;
  path_title: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  preview_path: string | null;
  download_path: string | null;
  docx_path: string | null;
};

// ── API calls ─────────────────────────────────────────────────────────────────

/** Latest career path for the current candidate, or null if none generated. */
export async function fetchCareerPath(): Promise<CareerPath | null> {
  const res = await apiAuthFetch("/api/v1/career/path", { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Career path fetch failed: ${res.status}`);
  }
  const data: CareerPathResponse = await res.json();
  return data.path;
}

/** (Re)generate the candidate's career path from their profile. */
export async function generateCareerPath(): Promise<
  ReadyOrAccepted<CareerPath>
> {
  const res = await apiAuthFetch("/api/v1/career/path/generate", {
    method: "POST",
  });
  return parseReadyOrAccepted(res, (body) => {
    const data = body as CareerPathResponse;
    if (!data?.path) {
      throw new Error("No career path returned");
    }
    return data.path;
  });
}

/** Prioritize one career path title — unlocks job search along that direction.
 *  Pass selectedTitles (preferred first) to save the full confirmed set as
 *  target_titles, e.g. from the kickoff multi-select. */
export async function prioritizeCareerPath(
  title: string,
  selectedTitles?: string[],
): Promise<CareerPath> {
  const res = await apiAuthFetch("/api/v1/career/path/prioritize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      ...(selectedTitles && selectedTitles.length > 0
        ? { selected_titles: selectedTitles }
        : {}),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Prioritize path failed: ${res.status}`);
  }
  const data: CareerPathResponse = await res.json();
  if (!data.path) {
    throw new Error("No career path returned");
  }
  return data.path;
}

export async function fetchCareerPathResumes(): Promise<CareerPathResume[]> {
  const res = await apiAuthFetch("/api/v1/career/path-resumes", { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Fetch path resumes failed: ${res.status}`);
  }
  const data: { resumes: CareerPathResume[] } = await res.json();
  return data.resumes ?? [];
}

export async function generateCareerPathResumes(): Promise<
  ReadyOrAccepted<CareerPathResume[]>
> {
  const res = await apiAuthFetch("/api/v1/career/path-resumes/generate", {
    method: "POST",
  });
  return parseReadyOrAccepted(res, (body) => {
    const data = body as { resumes?: CareerPathResume[] };
    return data.resumes ?? [];
  });
}

export async function fetchCareerPathResumePreview(resumeId: string): Promise<string> {
  const res = await apiAuthFetch(
    `/api/v1/career/path-resumes/${resumeId}/download?format=html&print_dialog=false`
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `Preview failed: ${res.status}`);
  }
  return res.text();
}

export async function downloadCareerPathResumePdf(resumeId: string): Promise<void> {
  const res = await apiAuthFetch(
    `/api/v1/career/path-resumes/${resumeId}/download?format=pdf`
  );
  if (!res.ok) throw new Error(`PDF download failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function downloadCareerPathResumeDocx(resumeId: string): Promise<void> {
  const res = await apiAuthFetch(
    `/api/v1/career/path-resumes/${resumeId}/download?format=docx`
  );
  if (!res.ok) throw new Error(`Word download failed: ${res.status}`);
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match?.[1] ?? "career-path-resume.docx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** @deprecated Use preview/PDF/DOC helpers instead. */
export async function downloadCareerPathResume(resumeId: string): Promise<void> {
  await downloadCareerPathResumePdf(resumeId);
}

/**
 * Find jobs along the candidate's career path. Returns matches that already
 * exist in the DB immediately; the backend also kicks off an Apify top-up +
 * re-score, so `refreshing` is true while fresher roles are still arriving.
 */
export async function findJobsForPath(): Promise<FindJobsResult> {
  const res = await apiAuthFetch("/api/v1/career/path/find-jobs", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Find jobs failed: ${res.status}`);
  }
  return res.json();
}

// ── Career Intelligence (24-layer profile) ──────────────────────────────────
//
//   GET  /api/v1/career/intelligence           → stored profile (or null)
//   POST /api/v1/career/intelligence/generate   → (re)compute from resume/LI/chat
//
// Mirrors api/.../services/career_intelligence/schema.py. Every field is
// optional — the engine fills what it can from available data.

export type Prediction = {
  outcome?: string | null;
  confidence?: number | null;
};

export type MobilityOption = {
  role: string;
  kind?: string | null;
  feasibility_score?: number | null;
  time_required?: string | null;
  skill_gap?: string[];
};

export type HardSkill = {
  skill: string;
  evidence?: string | null;
  years?: number | null;
  recency?: string | null;
  proficiency?: string | null;
};

export type GapForRole = {
  target_role: string;
  missing_skills?: string[];
  missing_experience?: string[];
  missing_certifications?: string[];
  missing_leadership_signals?: string[];
  missing_industry_exposure?: string[];
};

export type CareerIntelligence = {
  version?: number;
  generated_at?: string | null;
  updated_at?: string | null;
  model?: string | null;
  data_completeness?: number | null;

  identity?: {
    personal_profile?: {
      full_name?: string | null;
      preferred_name?: string | null;
      current_location?: string | null;
      relocation_preferences?: string | null;
      work_authorization?: string | null;
      visa_status?: string | null;
      citizenship?: string | null;
      languages?: string[];
      timezone?: string | null;
    };
    career_preferences?: {
      work_mode?: string | null;
      travel_willingness?: string | null;
      industry_preference?: string[];
      company_size_preference?: string | null;
      startup_vs_enterprise?: string | null;
    };
  };
  career_dna?: {
    archetype_scores?: Record<string, number>;
    primary_archetype?: string | null;
    secondary_archetype?: string | null;
    rationale?: string | null;
  };
  experience?: {
    total_years?: number | null;
    role_history?: Array<{
      title?: string | null;
      function?: string | null;
      industry?: string | null;
      seniority?: string | null;
      duration_months?: number | null;
      team_size?: number | null;
      aarya_insights?: string[];
    }>;
    experience_vector?: Record<string, number | null>;
  };
  skills?: {
    hard_skills?: HardSkill[];
    soft_skills?: string[];
    future_skills?: string[];
  };
  achievements?: Record<string, string | string[] | null>;
  leadership?: {
    leadership_stage?: string | null;
    signals?: string[];
    executive_readiness_score?: number | null;
  };
  trajectory?: {
    promotion_velocity_months?: number | null;
    growth_path?: string[];
    career_momentum_score?: number | null;
  };
  learning?: {
    certifications?: string[];
    courses?: string[];
    learning_velocity?: number | null;
  };
  industry?: {
    industry_exposure?: string[];
    industry_depth?: Record<string, number>;
    transferability_score?: number | null;
  };
  functional?: { scores?: Record<string, number> };
  behavioral?: {
    working_style?: string[];
    decision_style?: string[];
    risk_appetite?: string | null;
  };
  brand?: Record<string, number | string | null>;
  network?: Record<string, number | null>;
  market?: Record<string, number | null>;
  compensation?: {
    current_market_value?: number | null;
    salary_range?: { min?: number | null; max?: number | null };
    total_compensation?: number | null;
    equity_potential?: string | null;
    compensation_growth_potential?: number | null;
  };
  mobility?: {
    adjacent_roles?: MobilityOption[];
    stretch_roles?: MobilityOption[];
    pivot_roles?: MobilityOption[];
  };
  goals?: {
    explicit_goals?: {
      desired_title?: string | null;
      desired_industry?: string | null;
      desired_salary?: number | null;
    };
    inferred_goals?: string[];
  };
  risk?: Record<string, number | string | null>;
  gap_analysis?: GapForRole[];
  prediction?: {
    most_likely_next_role?: Prediction;
    most_likely_promotion?: Prediction;
    outcome_3_year?: Prediction;
    outcome_5_year?: Prediction;
    outcome_10_year?: Prediction;
  };
  path_graph?: {
    conservative_path?: string[];
    accelerated_path?: string[];
    pivot_path?: string[];
    entrepreneur_path?: string[];
  };
  recommendations?: Record<string, string[]>;
  employability?: Record<string, number | null>;
  hidden_signals?: Record<string, number | null>;
  open_questions?: string[];
};

export type CareerIntelligenceResponse = {
  intelligence: CareerIntelligence | null;
};

/** The candidate's stored Career Intelligence, or null if not computed yet. */
export async function fetchCareerIntelligence(): Promise<CareerIntelligence | null> {
  const res = await apiAuthFetch("/api/v1/career/intelligence", {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Career intelligence fetch failed: ${res.status}`);
  }
  const data: CareerIntelligenceResponse = await res.json();
  return data.intelligence;
}

/**
 * (Re)compute the full 24-layer Career Intelligence from the candidate's
 * resume, LinkedIn, and chat data. May return immediately or accept a durable
 * background operation (202).
 */
export async function generateCareerIntelligence(): Promise<
  ReadyOrAccepted<CareerIntelligence>
> {
  const res = await apiAuthFetch("/api/v1/career/intelligence/generate", {
    method: "POST",
  });
  return parseReadyOrAccepted(res, (body) => {
    const data = body as CareerIntelligenceResponse;
    if (!data?.intelligence) {
      throw new Error("No career intelligence returned");
    }
    return data.intelligence;
  });
}
