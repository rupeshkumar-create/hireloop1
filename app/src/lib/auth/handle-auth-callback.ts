/**
 * Shared auth callback logic — OAuth code exchange and email token_hash verification.
 * Used by /auth/callback and /auth/confirm (legacy/template alias).
 */
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { SIGNUP_ROLE_COOKIE, type SignupRole } from "@/lib/auth/constants";
import { createClient } from "@/lib/supabase/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const OTP_TYPES: ReadonlySet<EmailOtpType> = new Set([
  "signup",
  "invite",
  "magiclink",
  "recovery",
  "email_change",
  "email",
]);

function parseRole(raw: string | undefined): SignupRole {
  return raw === "recruiter" ? "recruiter" : "candidate";
}

async function verifyEmailTokenHash(
  supabase: Awaited<ReturnType<typeof createClient>>,
  tokenHash: string,
  tokenType: string | null,
): Promise<string | null> {
  const preferred = tokenType && OTP_TYPES.has(tokenType as EmailOtpType)
    ? [tokenType as EmailOtpType]
    : [];
  const fallbacks: EmailOtpType[] = ["email", "signup", "magiclink"];
  const attempts = [...preferred, ...fallbacks.filter((t) => !preferred.includes(t))];

  let lastError: string | null = null;
  for (const type of attempts) {
    const { error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type,
    });
    if (!error) return null;
    lastError = error.message;
  }
  return lastError ?? "Invalid or expired link.";
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

  const cookieStore = await cookies();
  const roleCookie = cookieStore.get(SIGNUP_ROLE_COOKIE)?.value;
  const role = parseRole(roleCookie);

  const supabase = await createClient();

  if (code) {
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
  } else if (tokenHash) {
    const verifyError = await verifyEmailTokenHash(supabase, tokenHash, tokenType);
    if (verifyError) {
      const redirectUrl = new URL("/signup", origin);
      redirectUrl.searchParams.set("error", "verification_failed");
      redirectUrl.searchParams.set("message", verifyError);
      return NextResponse.redirect(redirectUrl);
    }
  } else {
    const redirectUrl = new URL("/signup", origin);
    redirectUrl.searchParams.set("error", "auth_failed");
    redirectUrl.searchParams.set(
      "message",
      "Sign-in link is incomplete or expired. Request a new link from the signup page.",
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
          errBody?.detail ?? "Account setup failed. Please try signing in again.",
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
        new URL(
          "/signup?error=auth_failed&message=Email+confirmed+but+no+session.+Request+a+new+sign-in+link.",
          origin,
        ),
      );
  response.cookies.set(SIGNUP_ROLE_COOKIE, "", { maxAge: 0, path: "/" });
  return response;
}
