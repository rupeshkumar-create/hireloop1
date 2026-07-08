/**
 * Authenticated API client for hireschema.com → api.hireschema.com
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await apiAuthFetch(path, {
    cache: "no-store",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!res.ok) {
    // Prefer JSON error detail (FastAPI), but gracefully fall back to plain text.
    const body = await res
      .json()
      .catch(async () => ({ detail: (await res.text().catch(() => "")) || res.statusText }));
    const detail = (body as { detail?: string }).detail;
    const message = detail?.trim() || res.statusText || `API ${res.status}`;
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
