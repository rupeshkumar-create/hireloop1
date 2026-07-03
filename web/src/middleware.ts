import { NextResponse, type NextRequest } from "next/server";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3001";

/**
 * Marketing site (port 3000) has no auth handlers. When Supabase Site URL points
 * here by mistake, OAuth lands as /?code=… — bounce those params to the app SPA.
 */
export function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  const hasAuthParams =
    searchParams.has("code") ||
    searchParams.has("token_hash") ||
    searchParams.has("error");

  if (!hasAuthParams) {
    return NextResponse.next();
  }

  const targetPath = searchParams.has("token_hash") ? "/auth/confirm" : "/auth/callback";
  const destination = new URL(targetPath, APP_URL);
  destination.search = request.nextUrl.search;
  return NextResponse.redirect(destination);
}

export const config = {
  matcher: ["/", "/signup", "/login"],
};
