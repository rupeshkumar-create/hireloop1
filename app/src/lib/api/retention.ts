import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type ReturnSummary = {
  ok: boolean;
  new_matches_count: number;
  since_visit_at: string | null;
  proactive_message: string | null;
  dashboard_deep_link?: string;
};

export async function fetchReturnSummary(): Promise<ReturnSummary> {
  const res = await apiAuthFetch("/api/v1/me/return-summary");
  if (!res.ok) {
    return { ok: false, new_matches_count: 0, since_visit_at: null, proactive_message: null };
  }
  return (await res.json()) as ReturnSummary;
}

export function markVisit(): void {
  void apiAuthFetch("/api/v1/me/visit", { method: "POST" }).catch(() => undefined);
}
