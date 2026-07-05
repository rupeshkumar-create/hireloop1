/**
 * Authenticated fetch to FastAPI — attaches Supabase access token (Bearer).
 * Required because the API validates JWT via Supabase Auth, not browser
 * cookies alone.
 *
 * Failure semantics:
 *   - If there is no Supabase session, we still fire the request (lets the
 *     API decide). The form layer can inspect `res.status === 401` and
 *     redirect to /signup.
 *   - If the Supabase SDK itself throws while fetching the session (e.g.
 *     network blip, expired refresh token), we LOG the underlying cause
 *     and proceed with no token. We never let a Supabase failure masquerade
 *     as "API down" — that confuses the user.
 *   - If the actual fetch to the API fails (network), we throw a tagged
 *     `ApiUnreachableError` so the form layer can show "API down" with
 *     confidence (vs the generic browser "Failed to fetch").
 */

import { createClient } from "@/lib/supabase/client";
import { DIRECT_API_URL, getApiBaseUrl } from "@/lib/api/base-url";

/**
 * Tagged error class so callers can distinguish a true API connectivity
 * failure from anything else (auth refresh failures, CORS, etc.).
 */
export class ApiUnreachableError extends Error {
  readonly url: string;
  readonly cause: unknown;
  constructor(url: string, cause: unknown) {
    const causeMsg = cause instanceof Error ? cause.message : String(cause);
    super(`Can't reach API at ${url}: ${causeMsg}`);
    this.name = "ApiUnreachableError";
    this.url = url;
    this.cause = cause;
  }
}

export async function getAccessToken(): Promise<string | null> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  } catch (err) {
    // Supabase getSession threw — most likely a transient network issue
    // reaching auth.supabase.co for a token refresh. Don't kill the request.
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.warn(
        "[auth-fetch] Supabase getSession() failed; continuing without token.",
        err
      );
    }
    return null;
  }
}

function resolveFetchBase(init: RequestInit): string {
  // Multipart uploads can run 30–90s while the CV is parsed. Next.js/Vercel
  // rewrites time out on long requests, so large bodies go direct to the API
  // (CORS is configured on FastAPI for app origins).
  if (typeof window !== "undefined" && init.body instanceof FormData) {
    return DIRECT_API_URL;
  }
  return getApiBaseUrl();
}

export async function apiAuthFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(init.headers);

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const base = resolveFetchBase(init);
  const url = `${base}${path}`;

  try {
    return await fetch(url, {
      ...init,
      headers,
      credentials: "same-origin",
    });
  } catch (err) {
    // Browser fetch only throws on genuine network failures (CORS, DNS,
    // connection refused, abort). NOT on 4xx/5xx — those return a Response.
    const displayUrl =
      typeof window !== "undefined" ? DIRECT_API_URL : base;
    throw new ApiUnreachableError(displayUrl, err);
  }
}

/**
 * Lightweight probe used by error handlers to confirm whether the API is
 * really down vs the issue being elsewhere (Supabase, browser extension,
 * etc.). Cheap, no auth, no credentials.
 */
export async function probeApiHealth(): Promise<
  | { ok: true }
  | { ok: false; reason: "timeout" | "network" | "non_ok"; status?: number }
> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 3000);
  try {
    const res = await fetch(`${getApiBaseUrl()}/api/v1/health`, {
      method: "GET",
      signal: controller.signal,
      // No credentials, no auth — simplest possible request, no preflight.
    });
    if (!res.ok) return { ok: false, reason: "non_ok", status: res.status };
    return { ok: true };
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      return { ok: false, reason: "timeout" };
    }
    return { ok: false, reason: "network" };
  } finally {
    window.clearTimeout(timeoutId);
  }
}
