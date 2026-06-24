/** Role hint cookie used by OAuth callback/bootstrap flows. */
export const SIGNUP_ROLE_COOKIE = "hireloop_signup_role";
export const SIGNUP_ROLE_MAX_AGE_SEC = 600;

export type SignupRole = "candidate" | "recruiter";
