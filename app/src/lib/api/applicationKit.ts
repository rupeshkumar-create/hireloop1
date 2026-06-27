import type { MatchedJob } from "@/lib/api/matches";
import { apiAuthFetch } from "@/lib/api/auth-fetch";

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

export type ApplicationKitResume = {
  resume_id: string | null;
  status: string;
  download_path: string | null;
};

export type ApplicationKitMockInterview = {
  mock_interview_id: string;
  path: string;
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
