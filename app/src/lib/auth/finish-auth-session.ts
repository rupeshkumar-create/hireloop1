/**
 * After Supabase session exists — bootstrap profile and return the in-app destination.
 */
import { ApiUnreachableError } from "@/lib/api/auth-fetch";
import { getApiBaseUrl, getServerApiBaseUrl } from "@/lib/api/base-url";

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
    throw new Error(data.detail ?? "Account setup failed. Please try signing in again.");
  }

  const resolvedRole = data.role ?? role;
  if (resolvedRole === "recruiter") {
    return data.is_new_user ? "/recruiter/onboarding" : "/recruiter/inbox";
  }
  return data.is_new_user ? "/onboarding" : "/dashboard";
}
