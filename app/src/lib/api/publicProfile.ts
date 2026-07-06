import { consumeSSEStream } from "@/lib/chat/sse";
import type { ChatChip, ChatStreamCallbacks } from "@/lib/chat/types";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type PublicIntelligence = {
  data_completeness?: number | null;
  career_dna?: {
    primary_archetype?: string | null;
    secondary_archetype?: string | null;
    rationale?: string | null;
    archetype_scores?: Record<string, number>;
  };
  employability?: {
    overall_score?: number | null;
    leadership_score?: number | null;
    technical_score?: number | null;
    market_fit_score?: number | null;
    future_readiness_score?: number | null;
    executive_potential_score?: number | null;
  };
  trajectory?: {
    career_momentum_score?: number | null;
    growth_path?: string[];
    promotion_velocity_months?: number | null;
  };
  prediction?: {
    most_likely_next_role?: string | null;
    next_role_confidence?: number | null;
    outcome_3_year?: string | null;
  };
  market?: {
    skill_demand_score?: number | null;
    role_demand_score?: number | null;
    future_proof_score?: number | null;
    in_demand_skills?: string[];
    top_missing_skills?: string[];
    grounded?: boolean;
  };
  skills?: {
    hard_skills?: Array<{
      skill?: string;
      proficiency?: string | null;
      years?: number | null;
    }>;
    soft_skills?: string[];
    future_skills?: string[];
  };
  achievements?: {
    highlights?: string[];
    revenue_generated?: string | null;
    users_acquired?: string | null;
    team_growth?: string | null;
  };
  leadership?: {
    leadership_stage?: string | null;
    executive_readiness_score?: number | null;
    signals?: string[];
  };
  learning?: {
    certifications?: string[];
    learning_velocity?: number | null;
  };
  industry?: {
    industry_exposure?: string[];
    transferability_score?: number | null;
  };
  functional?: { scores?: Record<string, number> };
  behavioral?: {
    working_style?: string[];
    risk_appetite?: string | null;
  };
  brand?: {
    personal_brand_score?: number | null;
    profile_completeness?: number | null;
  };
  mobility?: {
    relocation_openness?: string | null;
    remote_preference?: string | null;
  };
  goals?: {
    desired_title?: string | null;
    inferred_goals?: string[];
  };
  experience_vector?: {
    technical_years?: number | null;
    leadership_years?: number | null;
    strategic_years?: number | null;
    customer_facing_years?: number | null;
  };
  preferences?: {
    work_mode?: string | null;
    company_size_preference?: string | null;
    industry_preference?: string[];
  };
};

export type PublicProfile = {
  slug: string;
  display_name: string | null;
  avatar_url: string | null;
  headline: string | null;
  summary: string | null;
  current_title: string | null;
  current_company: string | null;
  years_experience: number | null;
  location_city: string | null;
  location_state: string | null;
  skills: string[];
  looking_for: string | null;
  linkedin_url: string | null;
  privacy_mode?: boolean;
  viewer_authenticated?: boolean;
  market?: string | null;
  intelligence?: PublicIntelligence | null;
  job_context?: {
    role_id: string;
    role_slug: string;
    title: string;
    company_name: string | null;
    recruiter_name: string | null;
  } | null;
  experience: Array<{
    title?: string | null;
    company?: string | null;
    description?: string | null;
    start_date?: string | null;
    end_date?: string | null;
  }>;
  education: Array<{
    institution?: string | null;
    degree?: string | null;
    field_of_study?: string | null;
    start_date?: string | null;
    end_date?: string | null;
  }>;
  contact: {
    email: string | null;
    phone: string | null;
    hidden: boolean;
    requires_registration?: boolean;
  };
  display_currency?: string;
  display_currency_resolved?: string;
};

export type PublicChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
};

const base = () => getApiBaseUrl();

export type FetchPublicProfileOptions = {
  roleSlug?: string | null;
};

export async function fetchPublicProfile(
  slug: string,
  options: FetchPublicProfileOptions = {},
): Promise<PublicProfile> {
  const params = new URLSearchParams();
  if (options.roleSlug?.trim()) {
    params.set("role", options.roleSlug.trim());
  }
  const qs = params.toString();
  const path = `/api/v1/public/profiles/${encodeURIComponent(slug)}${qs ? `?${qs}` : ""}`;
  const res = await apiAuthFetch(path);
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "Profile not found");
  }
  return res.json() as Promise<PublicProfile>;
}

export async function fetchPublicProfileChat(
  slug: string,
  visitorSessionId: string,
): Promise<PublicChatMessage[]> {
  const params = new URLSearchParams({ visitor_session_id: visitorSessionId });
  const res = await fetch(
    `${base()}/api/v1/public/profiles/${encodeURIComponent(slug)}/chat/messages?${params}`,
  );
  if (!res.ok) return [];
  const data = (await res.json()) as { messages?: PublicChatMessage[] };
  return data.messages ?? [];
}

export async function sendPublicProfileChat(
  slug: string,
  visitorSessionId: string,
  message: string,
): Promise<{ reply: string; messages: PublicChatMessage[] }> {
  const res = await fetch(
    `${base()}/api/v1/public/profiles/${encodeURIComponent(slug)}/chat/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        visitor_session_id: visitorSessionId,
      }),
    },
  );
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "Could not send message");
  }
  return res.json() as Promise<{ reply: string; messages: PublicChatMessage[] }>;
}

export async function streamPublicProfileChat(
  slug: string,
  visitorSessionId: string,
  message: string,
  callbacks: ChatStreamCallbacks = {},
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch(
    `${base()}/api/v1/public/profiles/${encodeURIComponent(slug)}/chat/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        visitor_session_id: visitorSessionId,
      }),
      signal,
    },
  );
  if (!res.ok || !res.body) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "Could not send message");
  }
  const result = await consumeSSEStream(res.body, { callbacks, signal });
  if (result.error) throw new Error(result.error);
  return result.text;
}

export function getOrCreateVisitorSessionId(slug: string): string {
  const key = `hireloop_public_chat_${slug}`;
  try {
    const existing = localStorage.getItem(key);
    if (existing) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem(key, id);
    return id;
  } catch {
    return crypto.randomUUID();
  }
}
