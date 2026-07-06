import { getApiBaseUrl } from "@/lib/api/base-url";

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

export async function fetchPublicProfile(slug: string): Promise<PublicProfile> {
  const res = await fetch(`${base()}/api/v1/public/profiles/${encodeURIComponent(slug)}`);
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
