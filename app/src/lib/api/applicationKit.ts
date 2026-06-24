import type { MatchedJob } from "@/lib/api/matches";

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
