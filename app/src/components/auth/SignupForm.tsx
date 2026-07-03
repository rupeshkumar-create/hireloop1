"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { SIGNUP_ROLE_COOKIE } from "@/lib/auth/constants";
import { finishAuthSession } from "@/lib/auth/finish-auth-session";
import { cn } from "@/lib/utils";
import { Button, Input } from "@/components/ui";

type Role = "candidate" | "recruiter";
type LoadingAction = "linkedin" | "email-send" | "email-verify" | "dev" | null;

const DEV_EMAIL_LOGIN = process.env.NEXT_PUBLIC_DEV_EMAIL_LOGIN === "true";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function SignupForm() {
  const supabase = createClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isSignIn = searchParams.get("mode") === "signin";
  const defaultRole = useMemo<Role>(
    () => (searchParams.get("role") === "recruiter" ? "recruiter" : "candidate"),
    [searchParams]
  );
  const [role, setRole] = useState<Role>(defaultRole);
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [infoMessage, setInfoMessage] = useState("");
  const [devEmail, setDevEmail] = useState("");
  const [devPassword, setDevPassword] = useState("");
  const [email, setEmail] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");

  useEffect(() => {
    const error = searchParams.get("error");
    const message = searchParams.get("message");
    const decodedMessage = message
      ? decodeURIComponent(message.replace(/\+/g, " "))
      : null;

    if (error) {
      setErrorMessage(decodeAuthError(error, decodedMessage));
      setInfoMessage("");
    } else if (decodedMessage) {
      setInfoMessage(decodedMessage);
    }

    // Supabase sometimes returns OAuth errors in the URL hash (client-only).
    const hash = window.location.hash.slice(1);
    if (hash) {
      const hashParams = new URLSearchParams(hash);
      const hashError = hashParams.get("error");
      const hashDesc = hashParams.get("error_description");
      if (hashError || hashDesc) {
        setErrorMessage(
          decodeAuthError(
            hashError ?? "auth_failed",
            hashDesc ? decodeURIComponent(hashDesc.replace(/\+/g, " ")) : null
          )
        );
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      }
    }
  }, [searchParams]);

  async function routeAfterAuth(
    resolvedRole: string | undefined,
    isNewUser: boolean | undefined,
  ) {
    const redirectParam = searchParams.get("redirect");
    const safeRedirect =
      redirectParam?.startsWith("/") && !redirectParam.startsWith("//")
        ? redirectParam
        : null;

    if (resolvedRole === "recruiter") {
      router.push(safeRedirect?.startsWith("/recruiter") ? safeRedirect : "/recruiter");
      return;
    }
    if (safeRedirect && !safeRedirect.startsWith("/recruiter")) {
      router.push(safeRedirect);
      return;
    }
    router.push(isNewUser ? "/onboarding" : "/dashboard");
  }

  async function handleLinkedInSignIn() {
    setLoadingAction("linkedin");
    setErrorMessage("");
    setInfoMessage("");
    document.cookie = `${SIGNUP_ROLE_COOKIE}=${role}; path=/; max-age=600; SameSite=Lax`;

    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "linkedin_oidc",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          // LinkedIn OIDC requires these scopes for Supabase to read profile + email.
          scopes: "openid profile email",
        },
      });
      if (error) {
        setErrorMessage(error.message);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleSendCode(e: React.FormEvent) {
    e.preventDefault();
    const addr = email.trim();
    if (!addr) return;
    setLoadingAction("email-send");
    setErrorMessage("");
    setInfoMessage("");
    // Same role cookie as LinkedIn so /auth/bootstrap provisions the right side.
    document.cookie = `${SIGNUP_ROLE_COOKIE}=${role}; path=/; max-age=600; SameSite=Lax`;
    try {
      const redirectTo = `${window.location.origin}/auth/confirm`;
      const { error } = await supabase.auth.signInWithOtp({
        email: addr,
        options: {
          shouldCreateUser: true, // same flow signs up new users and signs in returning ones
          emailRedirectTo: redirectTo,
        },
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      setOtpSent(true);
      setInfoMessage("");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Couldn't send the code.");
    } finally {
      setLoadingAction(null);
    }
  }

  async function verifyEmailOtp(token: string) {
    const addr = email.trim();
    const attempts: Array<"email" | "signup"> = ["email", "signup"];
    let lastError: string | null = null;
    for (const type of attempts) {
      const { error } = await supabase.auth.verifyOtp({
        email: addr,
        token,
        type,
      });
      if (!error) return null;
      lastError = error.message;
    }
    return lastError ?? "Invalid or expired code.";
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    const token = otpCode.trim();
    if (token.length < 6) return;
    setLoadingAction("email-verify");
    setErrorMessage("");
    try {
      const verifyError = await verifyEmailOtp(token);
      if (verifyError) {
        setErrorMessage(
          `${verifyError} If your email only has a confirmation link, tap that link instead of entering a code.`,
        );
        return;
      }
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErrorMessage("Verified, but no session was created. Please try again.");
        return;
      }
      const destination = await finishAuthSession(session.access_token, role);
      document.cookie = `${SIGNUP_ROLE_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
      router.replace(destination);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Verification failed.",
      );
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleDevEmailSignIn(e: React.FormEvent) {
    e.preventDefault();
    if (!DEV_EMAIL_LOGIN) return;
    setLoadingAction("dev");
    setErrorMessage("");
    setInfoMessage("");
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: devEmail.trim(),
        password: devPassword,
      });
      if (error) {
        setErrorMessage(
          error.message === "Invalid login credentials"
            ? "Invalid email or password. Demo users must exist in Supabase Auth — run scripts/seed_dev.sql on your project."
            : error.message,
        );
        return;
      }
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErrorMessage("Sign-in succeeded but no session was created.");
        return;
      }
      document.cookie = `${SIGNUP_ROLE_COOKIE}=${role}; path=/; max-age=600; SameSite=Lax`;
      const bootstrapRes = await fetch(`${API_URL}/api/v1/auth/bootstrap`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ role }),
      });
      const data = (await bootstrapRes.json().catch(() => ({}))) as {
        role?: string;
        is_new_user?: boolean;
        detail?: string;
      };
      if (!bootstrapRes.ok) {
        setErrorMessage(data.detail ?? "Signed in but account setup failed.");
        return;
      }
      await routeAfterAuth(data.role, data.is_new_user);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Sign-in failed");
    } finally {
      setLoadingAction(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium text-ink-700">I am a…</p>
        <div className="grid grid-cols-2 gap-3">
          {(["candidate", "recruiter"] as Role[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRole(r)}
              className={cn(
                "border rounded-lg p-3 text-sm font-medium transition-all",
                role === r
                  ? "border-accent bg-ink-50 text-accent"
                  : "border-ink-100 text-ink-700 hover:border-ink-300"
              )}
            >
              {r === "candidate" ? "Job Seeker" : "Recruiter / Hiring Manager"}
            </button>
          ))}
        </div>
      </div>

      <Button
        type="button"
        variant="primary"
        size="lg"
        fullWidth
        disabled={loadingAction !== null}
        loading={loadingAction === "linkedin"}
        onClick={handleLinkedInSignIn}
        className="rounded-lg font-semibold"
      >
        {loadingAction === "linkedin" ? "Redirecting..." : "Continue with LinkedIn"}
      </Button>

      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-ink-100" />
        </div>
        <div className="relative flex justify-center bg-paper-1 px-2 text-xs text-ink-500">
          or continue with email
        </div>
      </div>

      {!otpSent ? (
        <form onSubmit={handleSendCode} className="space-y-3">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
          <Button
            type="submit"
            variant="primary"
            size="lg"
            fullWidth
            loading={loadingAction === "email-send"}
            disabled={!email.trim() || loadingAction !== null}
            className="rounded-lg font-semibold"
          >
            {loadingAction === "email-send" ? "Sending…" : "Email me a sign-in link"}
          </Button>
        </form>
      ) : (
        <div className="space-y-3">
          <div className="rounded-lg border border-ink-100 bg-paper-1 p-4 text-center">
            <p className="text-small font-medium text-ink-900">Check your email</p>
            <p className="mt-1 text-xs text-ink-500 leading-relaxed">
              We sent a sign-in link and a <strong>6-digit code</strong> to{" "}
              <span className="text-ink-800">{email}</span>. Enter the code below (most reliable with
              temp mail), or use the link and tap <strong>Continue</strong> on the next screen.
            </p>
            <p className="mt-2 text-[11px] text-ink-400 leading-relaxed">
              Link says invalid or expired? Request a fresh email — automated scanners often open
              links before you do. The code still works.
            </p>
          </div>

          <form onSubmit={handleVerifyCode} className="space-y-3">
            <Input
              type="text"
              inputMode="numeric"
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 10))}
              placeholder="6-digit code"
              autoComplete="one-time-code"
              required
            />
            <Button
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              loading={loadingAction === "email-verify"}
              disabled={otpCode.length < 6 || loadingAction !== null}
              className="rounded-lg"
            >
              {loadingAction === "email-verify" ? "Verifying…" : "Verify & continue"}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => {
              setOtpSent(false);
              setOtpCode("");
              setInfoMessage("");
            }}
            className="w-full text-xs text-ink-500 hover:text-ink-900"
          >
            Use a different email
          </button>
        </div>
      )}

      <p className="text-xs text-ink-500 text-center">
        Email sign-in sends a secure link to your inbox. Resume upload happens in onboarding.
      </p>

      {DEV_EMAIL_LOGIN && (
        <form onSubmit={handleDevEmailSignIn} className="space-y-3 rounded-lg border border-dashed border-ink-200 bg-ink-50/50 p-4">
          <p className="text-xs font-medium text-ink-700">
            Dev login {isSignIn ? "(sign in)" : ""}
          </p>
          <Input
            type="email"
            value={devEmail}
            onChange={(e) => setDevEmail(e.target.value)}
            placeholder="priya.candidate@hireloop.in"
            autoComplete="email"
            required
          />
          <Input
            type="password"
            value={devPassword}
            onChange={(e) => setDevPassword(e.target.value)}
            placeholder="Password"
            autoComplete="current-password"
            required
          />
          <button
            type="submit"
            disabled={loadingAction !== null}
            className="w-full rounded-lg border border-ink-200 bg-transparent py-2.5 text-sm font-medium text-ink-900 hover:bg-ink-50 hover:border-ink-300 disabled:opacity-60"
          >
            {loadingAction === "dev" ? "Signing in…" : "Sign in with email (dev)"}
          </button>
          <p className="text-[11px] text-ink-500 leading-snug">
            Candidate password: <span className="font-mono">DemoCandidate26!</span>
            {" · "}
            Recruiter password: <span className="font-mono">DemoRecruiter26!</span>
          </p>
          <p className="text-[11px] text-ink-500 leading-snug">
            e.g. <span className="font-mono">priya.candidate@hireloop.in</span>
            {" · "}
            <span className="font-mono">arun.recruiter@hireloop.in</span>
          </p>
        </form>
      )}

      {infoMessage && (
        <div className="rounded-lg border border-ink-100 bg-ink-50 p-3 text-small text-ink-700">
          {infoMessage}
        </div>
      )}

      {/* Error state */}
      {errorMessage && (
        <div className="rounded-lg bg-destructive-bg border border-destructive p-3 text-sm text-destructive">
          {errorMessage}
        </div>
      )}
    </div>
  );
}

function decodeAuthError(errorCode: string, message: string | null): string {
  if (
    message?.toLowerCase().includes("code challenge") ||
    message?.toLowerCase().includes("code verifier")
  ) {
    return (
      "Sign-in session expired or was interrupted. Close other Hireloop tabs, " +
      "clear cookies for this site, then try LinkedIn again in the same browser window."
    );
  }
  if (
    message?.toLowerCase().includes("external provider") ||
    message?.toLowerCase().includes("user profile")
  ) {
    return (
      "LinkedIn sign-in failed at Supabase Auth. Check: (1) Supabase → Authentication → " +
      "Providers → LinkedIn (OIDC) is enabled with valid Client ID/Secret, " +
      "(2) LinkedIn app has “Sign In with LinkedIn using OpenID Connect” product, " +
      "(3) LinkedIn redirect URL is https://blwudfxurykzyutkqkoi.supabase.co/auth/v1/callback, " +
      "(4) Supabase redirect URLs include https://hireloop1-app.vercel.app/auth/callback " +
      "and http://localhost:3001/auth/callback. " +
      "If config looks correct, upgrade GoTrue in Supabase → Settings → Infrastructure (≥ v2.149)."
    );
  }
  if (message) return message;
  switch (errorCode) {
    case "email_not_confirmed":
      return "Please confirm your email first, then sign in.";
    case "verification_failed":
      return "Email verification link failed or expired. Request a new one.";
    case "auth_failed":
      return "Authentication callback failed. Please try signing in again.";
    case "no_code":
      return "Missing auth code in callback. Please try again.";
    default:
      return "Authentication failed. Please try again.";
  }
}
