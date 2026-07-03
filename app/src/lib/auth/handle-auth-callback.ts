/**
 * Shared auth callback logic — OAuth code exchange only.
 * Email magic links land on /auth/confirm (user must click — avoids scanner burn).
 */
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SIGNUP_ROLE_COOKIE, type SignupRole } from "@/lib/auth/constants";
import { finishAuthSession } from "@/lib/auth/finish-auth-session";
import { createClient } from "@/lib/supabase/server";

function parseRole(raw: string | undefined): SignupRole {
  return raw === "recruiter" ? "recruiter" : "candidate";
}

export async function handleAuthCallback(request: Request): Promise<NextResponse> {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const tokenType = searchParams.get("type");
  const explicitNext = searchParams.get("next");
  const error = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");

  if (error) {
    const redirectUrl = new URL("/signup", origin);
    redirectUrl.searchParams.set("error", error);
    if (errorDescription) {
      redirectUrl.searchParams.set(
        "message",
        decodeURIComponent(errorDescription.replace(/\+/g, " ")),
      );
    }
    return NextResponse.redirect(redirectUrl);
  }

  // Legacy / misconfigured templates may still point at /auth/callback — forward to
  // the confirm interstitial without verifying (email scanners must not burn the token).
  if (tokenHash) {
    const confirmUrl = new URL("/auth/confirm", origin);
    confirmUrl.searchParams.set("token_hash", tokenHash);
    if (tokenType) confirmUrl.searchParams.set("type", tokenType);
    return NextResponse.redirect(confirmUrl);
  }

  const cookieStore = await cookies();
  const roleCookie = cookieStore.get(SIGNUP_ROLE_COOKIE)?.value;
  const role = parseRole(roleCookie);

  const supabase = await createClient();

  if (!code) {
    const redirectUrl = new URL("/signup", origin);
    redirectUrl.searchParams.set("error", "auth_failed");
    redirectUrl.searchParams.set(
      "message",
      "Sign-in link is incomplete or expired. Request a new link from the signup page.",
    );
    return NextResponse.redirect(redirectUrl);
  }

  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
  if (exchangeError) {
    const msg = exchangeError.message;
    const friendly =
      msg.toLowerCase().includes("code challenge") ||
      msg.toLowerCase().includes("code verifier")
        ? "Email link opened in a different browser than where you signed up. Request a new sign-in link on the signup page and open it in any browser."
        : msg;
    const redirectUrl = new URL("/signup", origin);
    redirectUrl.searchParams.set("error", "auth_failed");
    redirectUrl.searchParams.set("message", friendly);
    return NextResponse.redirect(redirectUrl);
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  let computedNext = role === "recruiter" ? "/recruiter" : "/dashboard";

  if (session?.access_token) {
    try {
      computedNext = await finishAuthSession(session.access_token, role);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Account setup failed. Please try signing in again.";
      const redirectUrl = new URL("/signup", origin);
      redirectUrl.searchParams.set("error", "bootstrap_failed");
      redirectUrl.searchParams.set("message", message);
      return NextResponse.redirect(redirectUrl);
    }
  }

  const isRealDeepLink =
    !!explicitNext && explicitNext.startsWith("/") && explicitNext !== "/onboarding";
  const safeNext = isRealDeepLink ? explicitNext : computedNext;
  const response = session?.access_token
    ? NextResponse.redirect(`${origin}${safeNext}`)
    : NextResponse.redirect(
        new URL(
          "/signup?error=auth_failed&message=Sign-in+completed+but+no+session.+Request+a+new+link.",
          origin,
        ),
      );
  response.cookies.set(SIGNUP_ROLE_COOKIE, "", { maxAge: 0, path: "/" });
  return response;
}
