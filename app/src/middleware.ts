import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // OAuth callback safety net. Supabase redirects to its configured Site URL
  // (the domain root) instead of our redirectTo (/auth/callback) when the
  // redirect URL isn't allow-listed for this deployment's domain. In that case
  // the auth `code` lands on "/" and nothing exchanges it, so the user just
  // sees the landing page. Forward it to the callback handler (same domain, so
  // the PKCE code_verifier cookie is preserved) to complete the sign-in.
  if (
    pathname === "/" &&
    (searchParams.has("code") || searchParams.has("token_hash"))
  ) {
    const url = request.nextUrl.clone();
    url.pathname = "/auth/callback";
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
