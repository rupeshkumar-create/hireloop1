/** Persist return path across OAuth / email auth round-trips. */

export const POST_AUTH_REDIRECT_KEY = "hireloop_post_auth_redirect";
export const POST_AUTH_REDIRECT_QUERY = "from";

export function isSafeRedirect(path: string | null | undefined): path is string {
  if (!path) return false;
  if (!path.startsWith("/") || path.startsWith("//")) return false;
  return true;
}

export function persistPostAuthRedirect(path: string): void {
  if (!isSafeRedirect(path)) return;
  try {
    sessionStorage.setItem(POST_AUTH_REDIRECT_KEY, path);
  } catch {
    /* private mode */
  }
}

export function readPostAuthRedirect(searchParams?: URLSearchParams | null): string | null {
  const fromQuery =
    searchParams?.get(POST_AUTH_REDIRECT_QUERY) ?? searchParams?.get("redirect");
  if (isSafeRedirect(fromQuery)) {
    return fromQuery;
  }

  if (typeof window !== "undefined") {
    try {
      const stored = sessionStorage.getItem(POST_AUTH_REDIRECT_KEY);
      if (isSafeRedirect(stored)) return stored;
    } catch {
      /* ignore */
    }
  }

  return null;
}

export function clearPostAuthRedirect(): void {
  try {
    sessionStorage.removeItem(POST_AUTH_REDIRECT_KEY);
  } catch {
    /* ignore */
  }
}

/** Recruiter sign-in / sign-up from a public candidate portfolio. */
export function recruiterAuthUrl(options: {
  from: string;
  mode?: "signin" | "signup";
}): string {
  const qs = new URLSearchParams();
  qs.set("role", "recruiter");
  if (options.mode === "signin") qs.set("mode", "signin");
  if (isSafeRedirect(options.from)) {
    qs.set(POST_AUTH_REDIRECT_QUERY, options.from);
  }
  return `/signup?${qs.toString()}`;
}
