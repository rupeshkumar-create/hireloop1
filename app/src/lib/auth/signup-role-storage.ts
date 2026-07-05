import { SIGNUP_ROLE_COOKIE, SIGNUP_ROLE_QUERY, parseSignupRole, type SignupRole } from "@/lib/auth/constants";

const SIGNUP_ROLE_SESSION_KEY = "hireloop_signup_role";

/** Persist role across OAuth / email round-trips (cookie + sessionStorage). */
export function persistSignupRole(role: SignupRole): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SIGNUP_ROLE_COOKIE}=${role}; path=/; max-age=3600; SameSite=Lax`;
  try {
    sessionStorage.setItem(SIGNUP_ROLE_SESSION_KEY, role);
  } catch {
    /* private mode */
  }
}

export function readSignupRole(searchParams?: URLSearchParams | null): SignupRole {
  if (typeof window !== "undefined") {
    for (const key of [SIGNUP_ROLE_QUERY, "role"] as const) {
      const fromQuery = searchParams?.get(key);
      if (fromQuery) return parseSignupRole(fromQuery);
    }

    try {
      const fromSession = sessionStorage.getItem(SIGNUP_ROLE_SESSION_KEY);
      if (fromSession) return parseSignupRole(fromSession);
    } catch {
      /* ignore */
    }

    const fromCookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith(`${SIGNUP_ROLE_COOKIE}=`))
      ?.split("=")[1];
    if (fromCookie) return parseSignupRole(fromCookie);
  }

  const fromQuery =
    searchParams?.get(SIGNUP_ROLE_QUERY) ?? searchParams?.get("role");
  return parseSignupRole(fromQuery ?? undefined);
}

export function clearSignupRole(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SIGNUP_ROLE_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
  try {
    sessionStorage.removeItem(SIGNUP_ROLE_SESSION_KEY);
  } catch {
    /* ignore */
  }
}

/** Signup URL that restores the Job Seeker vs Recruiter tab. */
export function signupUrl(
  role: SignupRole,
  params?: { error?: string; message?: string },
): string {
  const qs = new URLSearchParams();
  if (role === "recruiter") {
    qs.set("role", "recruiter");
    qs.set(SIGNUP_ROLE_QUERY, "recruiter");
  }
  if (params?.error) qs.set("error", params.error);
  if (params?.message) qs.set("message", params.message);
  const tail = qs.toString();
  return tail ? `/signup?${tail}` : "/signup";
}

/** OAuth redirect target — no query string (must match Supabase allow-list exactly). */
export function oauthCallbackUrl(): string {
  if (typeof window === "undefined") return "/auth/callback";
  return `${window.location.origin}/auth/callback`;
}
