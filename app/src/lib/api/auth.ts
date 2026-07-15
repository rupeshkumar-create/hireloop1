/**
 * Auth session helpers — GET /api/v1/auth/me
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import type { ActiveRole } from "@/lib/api/role";

export type AuthMe = {
  id: string;
  email: string;
  role: ActiveRole | "admin";
  phone_verified: boolean;
  full_name: string | null;
  has_candidate: boolean;
  has_recruiter: boolean;
  can_switch_roles: boolean;
};

export function canSwitchRoles(me: Pick<AuthMe, "has_candidate" | "has_recruiter">): boolean {
  return me.has_candidate && me.has_recruiter;
}

export async function fetchAuthMe(): Promise<AuthMe> {
  const res = await apiAuthFetch("/api/v1/auth/me");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `Auth me failed: ${res.status}`);
  }
  return res.json() as Promise<AuthMe>;
}
