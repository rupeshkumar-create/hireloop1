/**
 * After Supabase session exists — bootstrap profile and return the in-app destination.
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function finishAuthSession(
  accessToken: string,
  role: "candidate" | "recruiter",
): Promise<string> {
  const res = await fetch(`${API_URL}/api/v1/auth/bootstrap`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ role }),
  });

  const data = (await res.json().catch(() => ({}))) as {
    role?: string;
    is_new_user?: boolean;
    detail?: string;
  };

  if (!res.ok) {
    throw new Error(data.detail ?? "Account setup failed. Please try signing in again.");
  }

  const resolvedRole = data.role ?? role;
  if (resolvedRole === "recruiter") return "/recruiter";
  return data.is_new_user ? "/onboarding" : "/dashboard";
}
