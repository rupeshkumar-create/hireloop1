/**
 * Sign out — clears the Supabase session (server-side, removes auth cookies)
 * and redirects to the login page.
 *
 * Supports both GET (so a plain <Link href="/auth/signout"> works) and POST
 * (for form submissions / fetch). Either way we end on /login.
 */
import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

async function signOutAndRedirect(request: Request) {
  const { origin } = new URL(request.url);
  const supabase = await createClient();

  // Only attempt sign-out if there is an active session — avoids noisy errors.
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) {
    await supabase.auth.signOut();
  }

  return NextResponse.redirect(new URL("/login", origin), {
    // 303 forces a GET on the redirect target, even for POST requests.
    status: 303,
  });
}

export async function GET(request: Request) {
  return signOutAndRedirect(request);
}

export async function POST(request: Request) {
  return signOutAndRedirect(request);
}
