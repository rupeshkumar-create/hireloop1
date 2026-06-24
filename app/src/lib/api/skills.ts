import { apiAuthFetch } from "@/lib/api/auth-fetch";

/**
 * Autocomplete suggestions from the backend's ~2000-skill canonical vocabulary
 * (GET /api/v1/skills/suggest). Returns [] on empty query or any error so the
 * caller can render gracefully.
 */
export async function fetchSkillSuggestions(query: string, limit = 8): Promise<string[]> {
  const q = query.trim();
  if (!q) return [];
  try {
    const res = await apiAuthFetch(
      `/api/v1/skills/suggest?q=${encodeURIComponent(q)}&limit=${limit}`
    );
    if (!res.ok) return [];
    const data = (await res.json()) as { suggestions?: string[] };
    return Array.isArray(data.suggestions) ? data.suggestions : [];
  } catch {
    return [];
  }
}
