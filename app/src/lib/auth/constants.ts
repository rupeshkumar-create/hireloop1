/** Role hint cookie used by OAuth callback/bootstrap flows. */
export const SIGNUP_ROLE_COOKIE = "hireloop_signup_role";
export const SIGNUP_ROLE_MAX_AGE_SEC = 600;

/** Query param echoed on OAuth redirectTo — survives LinkedIn round-trip when cookies do not. */
export const SIGNUP_ROLE_QUERY = "signup_role";

export type SignupRole = "candidate" | "recruiter";

export function parseSignupRole(raw: string | null | undefined): SignupRole {
  return raw === "recruiter" ? "recruiter" : "candidate";
}
