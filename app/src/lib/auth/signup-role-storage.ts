import {
  SIGNUP_ROLE_COOKIE,
  SIGNUP_ROLE_MAX_AGE_SEC,
  SIGNUP_ROLE_QUERY,
  parseSignupRole,
  type SignupRole,
} from "@/lib/auth/constants";

const SIGNUP_ROLE_SESSION_KEY = "hireloop_signup_role";

/** Persist role across OAuth / email round-trips (cookie + sessionStorage). */
export function persistSignupRole(role: SignupRole): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SIGNUP_ROLE_COOKIE}=${role}; path=/; max-age=${SIGNUP_ROLE_MAX_AGE_SEC}; SameSite=Lax`;
  try {
    sessionStorage.setItem(SIGNUP_ROLE_SESSION_KEY, role);
  } catch {
    /* private mode */
  }
}

/**
 * Prefer the URL query (survives LinkedIn / email redirects), then session, then cookie.
 * Defaults to candidate so a stale recruiter cookie cannot hijack Job Seeker OAuth.
 */
export function readSignupRole(searchParams?: URLSearchParams | null): SignupRole {
  const fromParams =
    searchParams?.get(SIGNUP_ROLE_QUERY) ?? searchParams?.get("role") ?? null;
  if (fromParams) return parseSignupRole(fromParams);

  if (typeof window !== "undefined") {
    const urlParams = new URLSearchParams(window.location.search);
    const fromWindow =
      urlParams.get(SIGNUP_ROLE_QUERY) ?? urlParams.get("role") ?? null;
    if (fromWindow) return parseSignupRole(fromWindow);

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

  return "candidate";
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
  qs.set("role", role);
  qs.set(SIGNUP_ROLE_QUERY, role);
  if (params?.error) qs.set("error", params.error);
  if (params?.message) qs.set("message", params.message);
  return `/signup?${qs.toString()}`;
}

/**
 * LinkedIn OAuth redirect — always embeds signup_role so Job Seeker vs Recruiter
 * survives the LinkedIn round-trip (parity with email OTP emailRedirectTo).
 * Supabase redirect allow-list must include `/auth/callback` (exact or `/**`).
 */
export function oauthCallbackUrl(role: SignupRole): string {
  if (typeof window === "undefined") {
    return `/auth/callback?${SIGNUP_ROLE_QUERY}=${role}`;
  }
  const url = new URL("/auth/callback", window.location.origin);
  url.searchParams.set(SIGNUP_ROLE_QUERY, role);
  return url.toString();
}
