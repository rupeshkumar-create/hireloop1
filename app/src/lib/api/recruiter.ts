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
  public_slug?: string | null;
  public_listing_enabled?: boolean;
  public_role_url?: string | null;
  company_name?: string | null;
  calendly_url?: string | null;
  jd_bias_report?: JdBiasReport | null;
  interview_kit?: InterviewKit | null;
  calibration_candidates?: CalibrationEntry[] | null;
};

export type JdBiasIssue = {
  category: string;
  phrase: string;
  message: string;
  suggestion: string;
};

export type JdBiasReport = {
  passed: boolean;
  score: number;
  issues: JdBiasIssue[];
  summary: string;
};

export type CalibrationEntry = {
  candidate_id?: string;
  inbound_applicant_id?: string;
  verdict: "ideal" | "borderline" | "reject";
};

export type InterviewKit = {
  role_title: string;
  summary: string;
  stages: Array<{
    name: string;
    duration_minutes: number;
    goal: string;
    questions: string[];
  }>;
  scorecard: Array<{
    criterion: string;
    weight: number;
    rubric: Record<string, string>;
  }>;
  nice_to_probe: string[];
  red_flags: string[];
};

export type MarketIntel = {
  market: string;
  role_title: string;
  total_similar_roles: number;
  comp: Record<string, unknown>;
  competitors: Array<{ company_name: string; open_roles: number }>;
  skills_in_demand: string[];
  skill_gaps: Array<{ skill: string; pct_of_similar_roles: number; message: string }>;
  grounded: boolean;
};

export type RecruiterNudge = {
  type: string;
  severity: string;
  count: number;
  message: string;
  action: string;
  href: string;
};

export type PipelineRow = {
  id: string;
  stage: string;
  match_score: number | null;
  display_name: string;
  headline: string | null;
  current_title: string | null;
  years_experience: number | null;
  moved_at: string;
  notes?: string | null;
  source_type?: "platform" | "inbound";
  candidate_id?: string | null;
  inbound_applicant_id?: string | null;
  skills_matched?: string[] | null;
  skills_gap?: string[] | null;
  email?: string | null;
};

export type CreateRolePayload = {
  title: string;
  jd_text?: string | null;
  company_name?: string | null;
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

export type ImportRoleUrlResponse = {
  title: string | null;
  jd_text: string | null;
  company_name: string | null;
  comp_min_lpa: number | null;
  comp_max_lpa: number | null;
  location_city: string | null;
  location_state: string | null;
  remote_policy: string | null;
  seniority: string | null;
  source_url: string;
  source_type: string;
  extraction?: Record<string, unknown> | null;
  warnings: string[];
  ready_for_brief: boolean;
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
  calendly_url: string;
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

export type RecruiterRoleSummary = {
  id: string;
  title: string | null;
  location_city: string | null;
  status: string | null;
};

export type RecruiterProfile = {
  recruiter_id: string;
  title: string | null;
  company_name: string | null;
  company_id: string | null;
  onboarding_complete: boolean;
  hiring_focus: string | null;
  hiring_focus_source?: "roles" | "manual";
  profile_from_roles?: boolean;
  active_roles?: RecruiterRoleSummary[];
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
  public_role_url?: string | null;
  /** Progress signals for the "next step" hint on the roles list. */
  has_brief?: boolean;
  published?: boolean;
  pipeline_count?: number;
};

/** The single most useful thing to do next for a role. */
export function roleNextStep(role: RoleListItem): { label: string; tab: "intake" | "pipeline" } {
  if (!role.has_brief) {
    return { label: "Finish the brief with Nitya", tab: "intake" };
  }
  if (!role.published) {
    return { label: "Publish to request intros", tab: "intake" };
  }
  if (!role.pipeline_count) {
    return { label: "Run candidate search", tab: "intake" };
  }
  return { label: `${role.pipeline_count} in pipeline — review`, tab: "pipeline" };
}

export type RecruiterDashboardChat = {
  id: string;
  title: string | null;
  role_id: string | null;
  role_title: string | null;
  role_status: string | null;
  updated_at: string;
  last_message: string;
};

export type RecruiterDashboardStats = {
  active_roles: number;
  pipeline_total: number;
  pending_intros: number;
};

export type RecruiterDashboardData = {
  stats: RecruiterDashboardStats;
  chats: RecruiterDashboardChat[];
  roles: Array<{
    id: string;
    title: string;
    status: string;
    location_city: string | null;
    pipeline_count: number;
    updated_at?: string;
    public_role_url?: string | null;
  }>;
};

export type RecruiterCandidateSearchHit = {
  candidate_id: string;
  display_name: string;
  headline: string | null;
  summary?: string | null;
  current_title: string | null;
  current_company: string | null;
  location_city: string | null;
  location_state?: string | null;
  years_experience: number | null;
  looking_for?: string | null;
  skills?: string[];
  role_id: string | null;
  role_title: string | null;
  pipeline_stage: string | null;
  match_score: number | null;
  source: "pipeline" | "discover" | "platform";
  public_profile_url?: string | null;
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
  return apiFetch<RoleListItem[]>("/api/v1/recruiter/roles", { cache: "no-store" });
}

export async function fetchRecruiterDashboard(): Promise<RecruiterDashboardData> {
  return apiFetch<RecruiterDashboardData>("/api/v1/recruiter/dashboard", {
    cache: "no-store",
  });
}

export async function listRecruiterCandidates(
  query?: string,
  roleId?: string,
  limit = 50,
): Promise<{ query: string | null; count: number; candidates: RecruiterCandidateSearchHit[] }> {
  const params = new URLSearchParams();
  if (query?.trim()) params.set("q", query.trim());
  if (roleId) params.set("role_id", roleId);
  params.set("limit", String(limit));
  const qs = params.toString();
  return apiFetch(`/api/v1/recruiter/candidates${qs ? `?${qs}` : ""}`, { cache: "no-store" });
}

export async function searchRecruiterCandidates(
  query: string,
  roleId?: string,
): Promise<{ query: string; count: number; candidates: RecruiterCandidateSearchHit[] }> {
  const params = new URLSearchParams({ q: query });
  if (roleId) params.set("role_id", roleId);
  return apiFetch(`/api/v1/recruiter/candidates/search?${params.toString()}`);
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

export async function importRoleFromUrl(
  url: string,
): Promise<ImportRoleUrlResponse> {
  return apiFetch<ImportRoleUrlResponse>("/api/v1/recruiter/roles/import-url", {
    method: "POST",
    body: JSON.stringify({ url }),
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

export async function publishRole(roleId: string): Promise<{
  job_id?: string;
  status?: string;
  public_slug?: string;
  public_role_url?: string;
  public_listing_enabled?: boolean;
  error?: string;
}> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/publish`, { method: "POST" });
}

export async function movePipelineCandidate(
  roleId: string,
  pipelineId: string,
  payload: { stage?: string; notes?: string }
): Promise<{ ok: boolean }> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/pipeline/${pipelineId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function fetchPipeline(roleId: string): Promise<PipelineRow[]> {
  return apiFetch<PipelineRow[]>(`/api/v1/recruiter/roles/${roleId}/pipeline`, {
    cache: "no-store",
  });
}

export async function runJdBiasCheck(roleId: string): Promise<{ report: JdBiasReport; role: RecruiterRole }> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/jd-bias-check`, { method: "POST" });
}

export async function fetchSalarySuggestion(roleId: string): Promise<{
  comp_min: number | null;
  comp_max: number | null;
  suggestion: Record<string, unknown>;
}> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/salary-suggestion`);
}

export async function fetchMarketIntel(
  roleId: string,
  refresh = false
): Promise<{ intel: MarketIntel; cached: boolean }> {
  const qs = refresh ? "?refresh=true" : "";
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/market-intel${qs}`);
}

export async function fetchInterviewKit(
  roleId: string,
  refresh = false
): Promise<{ kit: InterviewKit; cached: boolean }> {
  const qs = refresh ? "?refresh=true" : "";
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/interview-kit${qs}`);
}

export async function setRoleCalibration(
  roleId: string,
  entries: CalibrationEntry[]
): Promise<{ calibration: CalibrationEntry[]; role: RecruiterRole }> {
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/calibration`, {
    method: "PUT",
    body: JSON.stringify({ entries }),
  });
}

export async function fetchRecruiterNudges(roleId?: string): Promise<{ nudges: RecruiterNudge[] }> {
  const qs = roleId ? `?role_id=${encodeURIComponent(roleId)}` : "";
  return apiFetch(`/api/v1/recruiter/nudges${qs}`, { cache: "no-store" });
}

export async function addExternalApplicant(
  roleId: string,
  payload: {
    full_name: string;
    email?: string;
    linkedin_url?: string;
    resume?: File;
  }
): Promise<{ applicant_id: string; full_name: string; match_score: number | null }> {
  const form = new FormData();
  form.set("full_name", payload.full_name);
  if (payload.email) form.set("email", payload.email);
  if (payload.linkedin_url) form.set("linkedin_url", payload.linkedin_url);
  if (payload.resume) form.set("resume", payload.resume);
  return apiFetch(`/api/v1/recruiter/roles/${roleId}/applicants`, {
    method: "POST",
    body: form,
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
