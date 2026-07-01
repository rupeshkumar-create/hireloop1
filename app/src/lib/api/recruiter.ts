import { apiFetch } from "@/lib/api/client";
import { formatSalaryRange } from "@/lib/salary";
import type { MarketCode } from "@/lib/markets";

export type ReadinessItem = {
  key: string;
  label: string;
  done: boolean;
};

export type RoleReadiness = {
  items: ReadinessItem[];
  done_count: number;
  total: number;
  ready_for_search: boolean;
  ready_to_publish: boolean;
};

export type RecruiterRole = {
  id: string;
  title: string;
  jd_text: string | null;
  jd_structured: Record<string, unknown> | null;
  hiring_brief: string | null;
  candidate_pitch: string | null;
  evaluation_criteria: Array<{ criterion: string; weight: number }> | null;
  must_haves: string[] | null;
  nice_to_haves: string[] | null;
  status: string;
  comp_min: number | null;
  comp_max: number | null;
  location_city: string | null;
  location_state: string | null;
  remote_policy: string | null;
  pipeline_count?: number;
  readiness?: RoleReadiness;
};

export type CreateRolePayload = {
  title: string;
  jd_text?: string | null;
  duplicate_from_role_id?: string | null;
  comp_min_lpa?: number | null;
  comp_max_lpa?: number | null;
  location_city?: string | null;
  location_state?: string | null;
  remote_policy?: string | null;
  seniority?: string | null;
};

export type CreateRoleResponse = {
  role_id: string;
  conversation_id: string;
  role: RecruiterRole;
  extraction?: Record<string, unknown> | null;
  skip_intake: boolean;
  readiness: RoleReadiness;
};

export type UpdateRolePayload = Partial<{
  title: string;
  jd_text: string;
  comp_min_lpa: number;
  comp_max_lpa: number;
  location_city: string;
  location_state: string;
  remote_policy: string;
  hiring_brief: string;
  candidate_pitch: string;
  must_haves: string[];
  nice_to_haves: string[];
  status: string;
}>;

export type NityaChatResponse = {
  reply: string;
  brief_generated: boolean;
  brief_complete?: boolean;
  chip_suggestions: string[];
  turn_count: number;
  max_turns: number;
  readiness: RoleReadiness;
  role: RecruiterRole;
  action_count: number;
  actions?: Array<{ type: string; at: string }>;
  candidates?: RankedCandidate[];
  published?: boolean;
  search_meta?: SearchMeta | null;
};

export type RankedCandidate = {
  candidate_id: string;
  pipeline_id?: string | null;
  stage?: string;
  overall_score: number;
  display_name?: string | null;
  headline?: string | null;
  summary?: string | null;
  current_title?: string | null;
  current_company?: string | null;
  years_experience?: number | null;
  location_city?: string | null;
  location_state?: string | null;
  skills?: string[];
  skills_matched?: string[];
  skills_gap?: string[];
  looking_for?: string | null;
  remote_preference?: string | null;
  notice_period_days?: number | null;
  expected_ctc_min?: number | null;
  expected_ctc_max?: number | null;
  current_ctc?: number | null;
  match_explanation?: string | null;
  scores?: Record<string, number>;
};

export type SearchMeta = {
  diagnostic?: string | null;
  message?: string | null;
  published?: boolean;
};

export type RecruiterProfile = {
  recruiter_id: string;
  title: string | null;
  company_name: string | null;
  company_id: string | null;
  onboarding_complete: boolean;
  hiring_focus: string | null;
};

export type NityaChatHistory = {
  conversation_id: string;
  messages: Array<{ role: string; content: string; created_at?: string }>;
  candidates: RankedCandidate[];
  published: boolean;
  brief_complete: boolean;
};

export type RoleListItem = {
  id: string;
  title: string;
  status: string;
  location_city: string | null;
  comp_min: number | null;
  comp_max: number | null;
};

export function formatCompRange(
  compMin: number | null | undefined,
  compMax: number | null | undefined,
  opts?: { market?: MarketCode | string | null; currency?: string | null },
): string {
  return formatSalaryRange(compMin, compMax, opts) ?? "Not set";
}

/** @deprecated Use formatCompRange with market context instead. */
export function inrToLpa(inr: number | null | undefined): number | null {
  if (inr == null) return null;
  return Math.round(inr / 100_000);
}

export async function listRoles(): Promise<RoleListItem[]> {
  return apiFetch<RoleListItem[]>("/api/v1/recruiter/roles");
}

export async function getRole(roleId: string): Promise<RecruiterRole> {
  return apiFetch<RecruiterRole>(`/api/v1/recruiter/roles/${roleId}`);
}

export async function createRole(
  payload: CreateRolePayload
): Promise<CreateRoleResponse> {
  return apiFetch<CreateRoleResponse>("/api/v1/recruiter/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateRole(
  roleId: string,
  payload: UpdateRolePayload
): Promise<RecruiterRole> {
  return apiFetch<RecruiterRole>(`/api/v1/recruiter/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function reExtractRole(roleId: string): Promise<{
  role: RecruiterRole;
  extraction: Record<string, unknown>;
  readiness: RoleReadiness;
}> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/re-extract`, {
    method: "POST",
  });
}

export async function startRoleSearch(
  roleId: string,
  limit = 25
): Promise<{ count: number }> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/search`, {
    method: "POST",
    body: JSON.stringify({ limit, public_profiles: true }),
  });
}

export async function sendNityaMessage(
  roleId: string,
  content: string,
  bootstrap = false
): Promise<NityaChatResponse> {
  return apiFetch<NityaChatResponse>(
    `/api/v1/recruiter/roles/${roleId}/chat/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content, bootstrap }),
    }
  );
}

export async function requestCandidateIntro(
  roleId: string,
  candidateId: string,
  message?: string
): Promise<{ ok?: boolean; intro_id?: string; error?: string }> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/intro`, {
    method: "POST",
    body: JSON.stringify({ candidate_id: candidateId, message }),
  });
}

export async function publishRole(roleId: string): Promise<Record<string, unknown>> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/publish`, { method: "POST" });
}

export async function movePipelineCandidate(
  roleId: string,
  pipelineId: string,
  stage: string
): Promise<{ ok: boolean }> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/pipeline/${pipelineId}`, {
    method: "PATCH",
    body: JSON.stringify({ stage }),
  });
}

export async function fetchRecruiterProfile(): Promise<RecruiterProfile> {
  return apiFetch<RecruiterProfile>("/api/v1/recruiter/me");
}

export async function updateRecruiterProfile(payload: {
  company_name?: string;
  recruiter_title?: string;
  hiring_focus?: string;
  onboarding_complete?: boolean;
}): Promise<RecruiterProfile> {
  return apiFetch<RecruiterProfile>("/api/v1/recruiter/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchNityaChatHistory(
  roleId: string
): Promise<NityaChatHistory> {
  return apiFetch<NityaChatHistory>(
    `/api/v1/recruiter/roles/${roleId}/chat/messages`
  );
}

export async function publishAndRequestIntro(
  roleId: string,
  candidateId: string,
  message?: string
): Promise<{ ok?: boolean; intro_id?: string; error?: string }> {
  await publishRole(roleId);
  return requestCandidateIntro(roleId, candidateId, message);
}
