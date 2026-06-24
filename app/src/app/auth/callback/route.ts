/**
 * GET /auth/callback — Supabase auth callback handler.
 * Supports both OAuth code exchange and email token verification.
 */
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { SIGNUP_ROLE_COOKIE, type SignupRole } from "@/lib/auth/constants";
import { createClient } from "@/lib/supabase/server";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function parseRole(raw: string | undefined): SignupRole {
  return raw === "recruiter" ? "recruiter" : "candidate";
}

const OTP_TYPES: ReadonlySet<EmailOtpType> = new Set([
  "signup",
  "invite",
  "magiclink",
  "recovery",
  "email_change",
  "email",
]);

export async function GET(request: Request) {
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
        decodeURIComponent(errorDescription.replace(/\+/g, " "))
      );
    }
    return NextResponse.redirect(redirectUrl);
  }

  const cookieStore = await cookies();
  const roleCookie = cookieStore.get(SIGNUP_ROLE_COOKIE)?.value;
  const role = parseRole(roleCookie);

  const supabase = await createClient();

  if (code) {
    const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
    if (exchangeError) {
      console.error("Auth callback exchange error:", exchangeError.message);
      const redirectUrl = new URL("/signup", origin);
      redirectUrl.searchParams.set("error", "auth_failed");
      redirectUrl.searchParams.set("message", exchangeError.message);
      return NextResponse.redirect(redirectUrl);
    }
  } else if (tokenHash && tokenType && OTP_TYPES.has(tokenType as EmailOtpType)) {
    const { error: verifyError } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: tokenType as EmailOtpType,
    });
    if (verifyError) {
      const redirectUrl = new URL("/signup?mode=signin", origin);
      redirectUrl.searchParams.set("error", "verification_failed");
      redirectUrl.searchParams.set("message", verifyError.message);
      return NextResponse.redirect(redirectUrl);
    }
  } else if (!code && !tokenHash) {
    const redirectUrl = new URL("/signup", origin);
    redirectUrl.searchParams.set("error", "auth_failed");
    redirectUrl.searchParams.set(
      "message",
      "LinkedIn sign-in did not complete. Please try again."
    );
    return NextResponse.redirect(redirectUrl);
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  let computedNext = role === "recruiter" ? "/recruiter" : "/dashboard";

  if (session?.access_token) {
    try {
      const bootstrapRes = await fetch(`${API_URL}/api/v1/auth/bootstrap`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ role }),
      });
      if (bootstrapRes.ok) {
        const data = (await bootstrapRes.json().catch(() => null)) as
          | { role?: string; is_new_user?: boolean }
          | null;
        const resolvedRole = data?.role ?? role;
        if (resolvedRole === "recruiter") {
          computedNext = "/recruiter";
        } else {
          computedNext = data?.is_new_user ? "/onboarding" : "/dashboard";
        }
      } else {
        const errBody = (await bootstrapRes.json().catch(() => null)) as
          | { detail?: string }
          | null;
        const redirectUrl = new URL("/signup", origin);
        redirectUrl.searchParams.set("error", "bootstrap_failed");
        redirectUrl.searchParams.set(
          "message",
          errBody?.detail ?? "Account setup failed. Please try signing in again."
        );
        return NextResponse.redirect(redirectUrl);
      }
    } catch (err) {
      console.error("Auth bootstrap failed:", err);
    }
  }

  const isRealDeepLink =
    !!explicitNext && explicitNext.startsWith("/") && explicitNext !== "/onboarding";
  const safeNext = isRealDeepLink ? explicitNext : computedNext;
  const response = session?.access_token
    ? NextResponse.redirect(`${origin}${safeNext}`)
    : NextResponse.redirect(
        new URL("/signup?mode=signin&message=Email confirmed. Please sign in.", origin)
      );
  response.cookies.set(SIGNUP_ROLE_COOKIE, "", { maxAge: 0, path: "/" });
  return response;
}
