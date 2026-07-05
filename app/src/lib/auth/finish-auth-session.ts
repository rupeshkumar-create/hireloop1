/**
 * After Supabase session exists — bootstrap profile and return the in-app destination.
 */
import { ApiUnreachableError } from "@/lib/api/auth-fetch";
import { getApiBaseUrl, getServerApiBaseUrl } from "@/lib/api/base-url";
import { resolvePostAuthDestination } from "@/lib/auth/post-auth-destination";

export async function finishAuthSession(
  accessToken: string,
  role: "candidate" | "recruiter",
  options?: { appOrigin?: string },
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
      // OAuth callback runs server-side — don't wait forever if API is down.
      ...(typeof window === "undefined" ? { signal: AbortSignal.timeout(15_000) } : {}),
    });
  } catch (err) {
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
        ? "API is temporarily unavailable. Check NEXT_PUBLIC_API_URL and redeploy."
        : "Account setup failed. Please try signing in again.");
    throw new Error(detail);
  }

  const resolvedRole = data.role ?? role;
  return resolvePostAuthDestination(resolvedRole, Boolean(data.is_new_user));
}
