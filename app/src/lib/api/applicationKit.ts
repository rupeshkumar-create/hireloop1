import type { MatchedJob } from "@/lib/api/matches";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  createApplicationKitError,
  retryApplicationKitRequest,
} from "@/lib/api/application-kit-recovery";

/** Shape returned by GET /application-kits/jobs/{job_id}. */
export type JobApplicationKit = {
  id: string;
  job_id: string;
  job_title: string | null;
  company_name: string | null;
  cover_letter: string;
  interview_prep: string;
  tailored_resume_id: string | null;
  mock_interview_id: string | null;
  created_at: string;
  updated_at: string;
};

type PrepareApplicationKitResponse =
  | ApplicationKit
  | {
      status: "processing";
      saved: boolean;
      job_id: string;
      background_job_id?: string;
      message?: string;
    }
  | {
      status: "ready";
      saved: boolean;
      kit: JobApplicationKit;
    };

type ApplicationKitStatusResponse =
  | {
      status: "ready";
      saved: boolean;
      job_id: string;
      kit: JobApplicationKit;
      background_job?: ApplicationKitBackgroundJob | null;
    }
  | {
      status: "processing" | "failed" | "missing";
      saved: boolean;
      job_id: string;
      message?: string;
      background_job?: ApplicationKitBackgroundJob | null;
    };

type ApplicationKitBackgroundJob = {
  id: string;
  status: "pending" | "running" | "completed" | "failed" | string;
  attempts: number;
  max_attempts: number;
  updated_at: string | null;
  completed_at: string | null;
};

const APPLICATION_KIT_POLL_ATTEMPTS = 90;
const APPLICATION_KIT_POLL_INTERVAL_MS = 2_000;

async function applicationKitFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  try {
    return await retryApplicationKitRequest((attempt) => {
      const headers = new Headers(init.headers);
      headers.set("X-Retry-Attempt", String(attempt));
      return apiAuthFetch(path, { ...init, headers });
    });
  } catch (error) {
    throw createApplicationKitError(error);
  }
}

/**
 * Fetch the saved application kit (cover letter + interview prep) for a job.
 * Returns null when none exists yet (404), so callers can render gracefully.
 */
export async function getApplicationKitForJob(
  jobId: string
): Promise<JobApplicationKit | null> {
  const res = await applicationKitFetch(`/api/v1/application-kits/jobs/${jobId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Kit fetch failed: ${res.status}`);
  const data = (await res.json()) as { kit: JobApplicationKit };
  return data.kit;
}

async function getApplicationKitStatusForJob(
  jobId: string
): Promise<ApplicationKitStatusResponse> {
  const res = await applicationKitFetch(`/api/v1/application-kits/jobs/${jobId}/status`);
  if (!res.ok) {
    const body = await res.json().catch(async () => ({
      detail: (await res.text().catch(() => "")) || res.statusText,
    }));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail?.trim() || `Kit status failed: ${res.status}`);
  }
  return res.json() as Promise<ApplicationKitStatusResponse>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isApplicationKit(value: PrepareApplicationKitResponse): value is ApplicationKit {
  return "cover_letter" in value && "interview_prep" in value && "job" in value;
}

function kitRowToApplicationKit(kit: JobApplicationKit): ApplicationKit {
  const job: MatchedJob = {
    job_id: kit.job_id,
    title: kit.job_title ?? "Saved job",
    company_name: kit.company_name,
    location_city: null,
    location_state: null,
    is_remote: false,
    seniority: null,
    employment_type: null,
    ctc_min: null,
    ctc_max: null,
    salary_currency: null,
    skills_required: [],
    apply_url: null,
    overall_score: 0,
    skills_score: null,
    experience_score: null,
    location_score: null,
    ctc_score: null,
    explanation: null,
    computed_at: kit.updated_at,
    action_state: "kit_ready",
    action_label: "Kit ready",
  };

  return {
    kit_id: kit.id,
    saved: true,
    job,
    apply_url: null,
    cover_letter: kit.cover_letter,
    interview_prep: kit.interview_prep,
    resume: {
      resume_id: kit.tailored_resume_id,
      status: kit.tailored_resume_id ? "ready" : "unavailable",
      download_path: kit.tailored_resume_id
        ? `/api/v1/tailored-resumes/tailored/${kit.tailored_resume_id}/download`
        : null,
    },
    mock_interview: {
      mock_interview_id: kit.mock_interview_id,
      path: kit.mock_interview_id ? `/mock-interview/${kit.mock_interview_id}` : null,
    },
  };
}

async function pollApplicationKit(jobId: string): Promise<ApplicationKit> {
  let requeuedIncomplete = false;
  for (let attempt = 0; attempt < APPLICATION_KIT_POLL_ATTEMPTS; attempt += 1) {
    if (attempt > 0) {
      await sleep(APPLICATION_KIT_POLL_INTERVAL_MS);
    }
    const status = await getApplicationKitStatusForJob(jobId);
    if (status.status === "ready") {
      const kit = kitRowToApplicationKit(status.kit);
      if (kit.resume.resume_id) {
        return kit;
      }
      // Status should not return ready without resume; keep waiting if it does.
      continue;
    }
    if (status.status === "failed") {
      throw new Error(
        status.message ||
          "Application kit generation failed. Please retry from the job card."
      );
    }
    if (status.status === "missing" && !requeuedIncomplete) {
      // Incomplete prior kit (cover/prep only) — ask backend to generate again once.
      requeuedIncomplete = true;
      const res = await applicationKitFetch(
        `/api/v1/application-kits/jobs/${jobId}/prepare`,
        { method: "POST" },
      );
      if (res.ok) {
        const data = (await res.json()) as PrepareApplicationKitResponse;
        if (isApplicationKit(data)) return data;
        if (data.status === "ready") {
          const kit = kitRowToApplicationKit(data.kit);
          if (kit.resume.resume_id) return kit;
        }
      }
    }
  }

  throw new Error("Your application kit is still preparing. Please try again in a moment.");
}

/** Generate full application kit (resume + cover letter + interview prep) for a job. */
export async function prepareApplicationKit(jobId: string): Promise<ApplicationKit> {
  const res = await applicationKitFetch(
    `/api/v1/application-kits/jobs/${jobId}/prepare`,
    { method: "POST" },
  );
  if (!res.ok) {
    const body = await res.json().catch(async () => ({
      detail: (await res.text().catch(() => "")) || res.statusText,
    }));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail?.trim() || `Kit prepare failed: ${res.status}`);
  }
  const data = (await res.json()) as PrepareApplicationKitResponse;
  if (isApplicationKit(data)) {
    return data;
  }
  if (data.status === "ready") {
    return kitRowToApplicationKit(data.kit);
  }
  return pollApplicationKit(jobId);
}

/** Resume status polling without creating duplicate background work. */
export async function checkApplicationKit(jobId: string): Promise<ApplicationKit> {
  return pollApplicationKit(jobId);
}

/** Idempotently request generation again, then resume status polling. */
export async function retryApplicationKit(jobId: string): Promise<ApplicationKit> {
  return prepareApplicationKit(jobId);
}

export type ApplicationKitResume = {
  resume_id: string | null;
  status: string;
  download_path: string | null;
};

export type ApplicationKitMockInterview = {
  mock_interview_id: string | null;
  path: string | null;
};

export type ApplicationKit = {
  kit_id?: string | null;
  saved: boolean;
  job: MatchedJob;
  apply_url?: string | null;
  cover_letter: string;
  interview_prep: string;
  resume: ApplicationKitResume;
  mock_interview: ApplicationKitMockInterview;
};
