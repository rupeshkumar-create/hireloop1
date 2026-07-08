/**
 * After Supabase session exists — bootstrap profile and return the in-app destination.
 */
import { ApiUnreachableError } from "@/lib/api/auth-fetch";
import { getApiBaseUrl, getServerApiBaseUrl } from "@/lib/api/base-url";
import { resolvePostAuthDestination } from "@/lib/auth/post-auth-destination";
import {
  isSafeRedirect,
  readPostAuthRedirect,
} from "@/lib/auth/post-auth-redirect";

const BOOTSTRAP_TIMEOUT_MS = 30_000;

export async function finishAuthSession(
  accessToken: string,
  role: "candidate" | "recruiter",
  options?: { appOrigin?: string; redirect?: string | null },
): Promise<string> {
  const base =
    typeof window !== "undefined"
      ? getApiBaseUrl()
      : getServerApiBaseUrl(options?.appOrigin);
  let res: Response;
  try {
    res = await fetch(`${base}/api/v1/auth/bootstrap`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ role }),
      signal: AbortSignal.timeout(BOOTSTRAP_TIMEOUT_MS),
    });
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      throw new ApiUnreachableError(
        base,
        new Error(
          "Account setup timed out — the API may be unable to reach the database. Try again in a moment.",
        ),
      );
    }
    throw new ApiUnreachableError(base, err);
  }

  const data = (await res.json().catch(() => ({}))) as {
    role?: string;
    is_new_user?: boolean;
    detail?: string;
  };

  if (!res.ok) {
    const detail =
      data.detail ??
      (res.status === 502 || res.status === 503
        ? "Our servers are temporarily unavailable (database connection issue). Please try again in a minute."
        : "Account setup failed. Please try signing in again.");
    throw new Error(detail);
  }

  const resolvedRole = data.role ?? role;
  const savedRedirect =
    (options?.redirect && isSafeRedirect(options.redirect) ? options.redirect : null) ??
    readPostAuthRedirect();
  if (savedRedirect) {
    return savedRedirect;
  }
  return resolvePostAuthDestination(resolvedRole, Boolean(data.is_new_user));
}
