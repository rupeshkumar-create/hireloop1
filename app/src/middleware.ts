import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * - Apex → www canonical host
 * - OAuth `code` / email `token_hash` landed on the wrong path (Supabase Site URL
 *   fallback) → forward to /auth/callback or /auth/confirm
 *
 * Never rewrite `/hireloop-api/*` — those requests proxy to FastAPI. In particular,
 * Gmail OAuth returns `?code=` on `/hireloop-api/api/v1/gmail/callback`; stealing
 * that code for Supabase auth leaves `gmail_tokens` empty and Connect appears stuck.
 */
export function middleware(request: NextRequest) {
  const url = request.nextUrl.clone();
  const host = (request.headers.get("host") ?? "").split(":")[0].toLowerCase();

  if (host === "hireschema.com") {
    url.protocol = "https";
    url.host = "www.hireschema.com";
    return NextResponse.redirect(url, 308);
  }

  const pathname = url.pathname;

  // API proxy: pass through untouched (includes Google OAuth callback with ?code=).
  if (pathname.startsWith("/hireloop-api")) {
    return NextResponse.next();
  }

  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");

  if (code && pathname !== "/auth/callback") {
    url.pathname = "/auth/callback";
    return NextResponse.redirect(url);
  }

  if (
    tokenHash &&
    pathname !== "/auth/confirm" &&
    pathname !== "/auth/callback"
  ) {
    url.pathname = "/auth/confirm";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/:path*",
};
