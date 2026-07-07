import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type JobPipelineStage =
  | "saved"
  | "kit_ready"
  | "applied"
  | "screening"
  | "interview"
  | "offer"
  | "hired"
  | "rejected"
  | "withdrawn"
  | "intro_in_progress"
  | "intro_accepted"
  | "tracked";

export type JobPipelineItem = {
  job_id: string;
  title: string;
  company_name: string | null;
  location_city: string | null;
  location_state: string | null;
  is_remote: boolean | null;
  apply_url: string | null;
  stage: JobPipelineStage;
  saved: boolean;
  saved_at: string | null;
  kit_id: string | null;
  kit_updated_at: string | null;
  tailored_resume_id: string | null;
  mock_interview_id: string | null;
  application_status: string | null;
  applied_at: string | null;
  intro_id: string | null;
  intro_status: string | null;
  intro_direction: string | null;
  last_activity_at: string | null;
};

export async function fetchJobPipeline(): Promise<JobPipelineItem[]> {
  const res = await apiAuthFetch("/api/v1/me/job-pipeline", { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Job pipeline failed: ${res.status}`,
    );
  }
  const data = (await res.json()) as { items: JobPipelineItem[] };
  return data.items ?? [];
}
