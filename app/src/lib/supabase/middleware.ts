/**
 * Supabase middleware client — refreshes sessions on every request.
 * Used inside src/middleware.ts.
 */
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import type { Database } from "@/types/database";
import { getSupabasePublicEnv } from "@/lib/supabase/env";
import { SIGNUP_ROLE_COOKIE } from "@/lib/auth/constants";

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });
  const { url, anonKey } = getSupabasePublicEnv();

  const supabase = createServerClient<Database>(
    url,
    anonKey,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(
          cookiesToSet: Array<{ name: string; value: string; options?: Record<string, unknown> }>
        ) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            supabaseResponse.cookies.set(name, value, options as any)
          );
        },
      },
    }
  );

  // Refresh session — important for Server Component auth
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;

  // Protected routes: redirect unauthenticated users to /signup
  const protectedPaths = [
    "/dashboard",
    "/chat",
    "/jobs",
    "/profile",
    "/intros",
    "/recruiter",
    "/resumes",
    "/settings",
    "/admin",
    "/onboarding",
  ];
  const isProtected = protectedPaths.some((p) => pathname.startsWith(p));

  if (isProtected && !user) {
    const url = request.nextUrl.clone();
    url.pathname = "/signup";
    url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(url);
  }

  // Redirect authenticated users away from auth pages (unless showing an error).
  const authPaths = ["/signup", "/login"];
  const isAuthPage = authPaths.some((p) => pathname.startsWith(p));

  if (isAuthPage && user && !request.nextUrl.searchParams.has("error")) {
    const roleCookie = request.cookies.get(SIGNUP_ROLE_COOKIE)?.value;
    const url = request.nextUrl.clone();
    url.pathname = roleCookie === "recruiter" ? "/recruiter/inbox" : "/dashboard";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
