import type { MatchedJob } from "@/lib/api/matches";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import {
  parseReadyOrAccepted,
  type ReadyOrAccepted,
} from "@/lib/api/aiOperations";

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

/**
 * Fetch the saved application kit (cover letter + interview prep) for a job.
 * Returns null when none exists yet (404), so callers can render gracefully.
 */
export async function getApplicationKitForJob(
  jobId: string
): Promise<JobApplicationKit | null> {
  const res = await apiAuthFetch(`/api/v1/application-kits/jobs/${jobId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Kit fetch failed: ${res.status}`);
  const data = (await res.json()) as { kit: JobApplicationKit };
  return data.kit;
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

function parsePrepareReady(body: unknown): ApplicationKit {
  const data = body as PrepareApplicationKitResponse;
  if (isApplicationKit(data)) return data;
  if (data && typeof data === "object" && "status" in data && data.status === "ready") {
    return kitRowToApplicationKit(data.kit);
  }
  throw new Error("Application kit was not ready.");
}

/**
 * Start application kit generation. Returns the kit immediately when already
 * ready, otherwise an AiOperationAccepted for shared progress tracking.
 * Callers must track 202s via AiOperationsProvider and re-fetch the kit.
 */
export async function prepareApplicationKit(
  jobId: string,
): Promise<ReadyOrAccepted<ApplicationKit>> {
  const res = await apiAuthFetch(`/api/v1/application-kits/jobs/${jobId}/prepare`, {
    method: "POST",
  });
  return parseReadyOrAccepted(res, parsePrepareReady);
}

/** Load a ready kit after a durable prepare operation succeeds. */
export async function fetchReadyApplicationKit(jobId: string): Promise<ApplicationKit> {
  const kit = await getApplicationKitForJob(jobId);
  if (!kit) {
    throw new Error("Application kit is not ready yet.");
  }
  return kitRowToApplicationKit(kit);
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
