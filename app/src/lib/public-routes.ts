/** Paths that skip candidate gating, chat warmup, and other authed-only shell work. */
const PUBLIC_PREFIXES = [
  "/signup",
  "/login",
  "/auth",
  "/onboarding",
  "/voice",
  "/p/",
  "/r/",
] as const;

export function isPublicPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  if (pathname === "/") return true;
  return PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}
