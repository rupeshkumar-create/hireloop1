/**
 * Active-role switching — lets one login move between the candidate and
 * recruiter experiences. Calls POST /auth/role, which provisions the target
 * profile on demand and flips public.users.role.
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type ActiveRole = "candidate" | "recruiter";

export async function switchActiveRole(role: ActiveRole): Promise<ActiveRole> {
  const res = await apiAuthFetch("/api/v1/auth/role", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `Switch failed: ${res.status}`);
  }
  const data = (await res.json()) as { role: ActiveRole };
  return data.role;
}
