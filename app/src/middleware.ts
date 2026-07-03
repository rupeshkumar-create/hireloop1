import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // OAuth/email callback — must NOT run session refresh before exchangeCodeForSession.
  if (pathname.startsWith("/auth/callback") || pathname.startsWith("/auth/confirm")) {
    return NextResponse.next();
  }

  // OAuth callback safety net. Supabase redirects to its configured Site URL
  // (the domain root) instead of our redirectTo (/auth/callback) when the
  // redirect URL isn't allow-listed for this deployment's domain. In that case
  // the auth `code` — OR an `error` (e.g. bad_oauth_state) — lands on "/" and
  // nothing handles it, so the user just sees the landing page with a dirty
  // URL. Forward it to the callback handler (same domain, so the PKCE
  // code_verifier cookie is preserved): a `code` completes sign-in, an `error`
  // is turned into a friendly "sign-in failed, try again" on /signup — never
  // the email-verification screen.
  if (
    pathname === "/" &&
    (searchParams.has("code") ||
      searchParams.has("token_hash") ||
      searchParams.has("error"))
  ) {
    const url = request.nextUrl.clone();
    url.pathname = searchParams.has("token_hash") ? "/auth/confirm" : "/auth/callback";
    return NextResponse.redirect(url);
  }

  return await updateSession(request);
}

export const config = {
  matcher: [
    /*
     * Match all request paths EXCEPT:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (browser icon)
     * - public files (png, jpg, svg, etc.)
     * - /health (health-check route — no auth needed)
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|css|js|woff2?)$|health).*)",
  ],
};
