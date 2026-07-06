/** Map Supabase auth errors to user-facing copy — OAuth vs email are different flows. */

export type AuthErrorContext = "oauth" | "email" | "unknown";

export function detectAuthErrorContext(
  errorCode: string | null,
  message: string | null,
): AuthErrorContext {
  const code = (errorCode ?? "").toLowerCase();
  const msg = (message ?? "").toLowerCase();
  if (
    code.includes("oauth") ||
    msg.includes("linkedin") ||
    msg.includes("external provider") ||
    msg.includes("user profile")
  ) {
    return "oauth";
  }
  if (
    code.includes("otp") ||
    code.includes("email") ||
    msg.includes("magic link") ||
    msg.includes("6-digit")
  ) {
    return "email";
  }
  return "unknown";
}

export function formatPkceError(context: AuthErrorContext): string {
  if (context === "oauth") {
    return (
      "LinkedIn sign-in was interrupted or your session expired. " +
      "Close other Hireschema tabs, then tap Continue with LinkedIn again in this browser."
    );
  }
  if (context === "email") {
    return (
      "Email link opened in a different browser than where you signed up. " +
      "Request a new sign-in link on the signup page, or enter the 6-digit code from your email."
    );
  }
  return (
    "Sign-in session expired. Please try again in the same browser window where you started."
  );
}

export function decodeAuthError(
  errorCode: string,
  message: string | null,
  context: AuthErrorContext = "unknown",
): string {
  const resolvedContext =
    context === "unknown" ? detectAuthErrorContext(errorCode, message) : context;

  if (
    message?.toLowerCase().includes("code challenge") ||
    message?.toLowerCase().includes("code verifier") ||
    message?.toLowerCase().includes("invalid flow state") ||
    message?.toLowerCase().includes("already been used")
  ) {
    return formatPkceError(resolvedContext);
  }

  if (
    message?.toLowerCase().includes("external provider") ||
    message?.toLowerCase().includes("user profile")
  ) {
    return (
      "LinkedIn sign-in failed at Supabase Auth. Check: (1) Supabase → Authentication → " +
      "Providers → LinkedIn (OIDC) is enabled with valid Client ID/Secret, " +
      "(2) LinkedIn app has “Sign In with LinkedIn using OpenID Connect” product, " +
      "(3) LinkedIn redirect URL is your Supabase project URL + /auth/v1/callback, " +
      "(4) Supabase redirect URLs include your app URL + /auth/callback " +
      "(e.g. https://hireloop1-app.vercel.app/auth/callback and http://localhost:3001/auth/callback)."
    );
  }

  if (message) return message;

  switch (errorCode) {
    case "email_not_confirmed":
      return "Please confirm your email first, then sign in.";
    case "verification_failed":
      return "Email verification link failed or expired. Request a new one.";
    case "auth_failed":
      return resolvedContext === "oauth"
        ? "LinkedIn sign-in failed. Please try again."
        : "Authentication callback failed. Please try signing in again.";
    case "bootstrap_failed":
      return "Account setup failed. Check that the API is running and NEXT_PUBLIC_API_URL is set, then try again.";
    case "no_code":
      return "Missing auth code in callback. Please try again.";
    default:
      return resolvedContext === "oauth"
        ? "LinkedIn sign-in failed. Please try again."
        : "Authentication failed. Please try again.";
  }
}
