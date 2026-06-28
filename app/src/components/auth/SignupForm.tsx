"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { SIGNUP_ROLE_COOKIE } from "@/lib/auth/constants";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui";

type Role = "candidate" | "recruiter";

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
  const [isLoading, setIsLoading] = useState(false);
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
    if (message) {
      setInfoMessage(decodeURIComponent(message.replace(/\+/g, " ")));
    }
    if (error) {
      setErrorMessage(decodeAuthError(error, message));
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

  async function handleLinkedInSignIn() {
    setIsLoading(true);
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
      setIsLoading(false);
    }
  }

  async function handleSendCode(e: React.FormEvent) {
    e.preventDefault();
    const addr = email.trim();
    if (!addr) return;
    setIsLoading(true);
    setErrorMessage("");
    setInfoMessage("");
    // Same role cookie as LinkedIn so /auth/bootstrap provisions the right side.
    document.cookie = `${SIGNUP_ROLE_COOKIE}=${role}; path=/; max-age=600; SameSite=Lax`;
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email: addr,
        options: {
          shouldCreateUser: true, // same flow signs up new users and signs in returning ones
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      setOtpSent(true);
      setInfoMessage(`We emailed a 6-digit login code to ${addr}.`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Couldn't send the code.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    const token = otpCode.trim();
    if (token.length < 6) return;
    setIsLoading(true);
    setErrorMessage("");
    try {
      const { error } = await supabase.auth.verifyOtp({
        email: email.trim(),
        token,
        type: "email",
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErrorMessage("Verified, but no session was created. Please try again.");
        return;
      }
      // Mirror the OAuth callback: bootstrap the profile + route by role / new-user.
      const res = await fetch(`${API_URL}/api/v1/auth/bootstrap`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ role }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        role?: string;
        is_new_user?: boolean;
      };
      if (data.role === "recruiter") {
        router.push("/recruiter");
      } else {
        router.push(data.is_new_user ? "/onboarding" : "/dashboard");
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Verification failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDevEmailSignIn(e: React.FormEvent) {
    e.preventDefault();
    if (!DEV_EMAIL_LOGIN) return;
    setIsLoading(true);
    setErrorMessage("");
    setInfoMessage("");
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: devEmail.trim(),
        password: devPassword,
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErrorMessage("Sign-in succeeded but no session was created.");
        return;
      }
      const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!meRes.ok) {
        setErrorMessage("Signed in but could not load your profile.");
        return;
      }
      const me = (await meRes.json()) as { role?: string };
      router.push(me.role === "recruiter" ? "/recruiter" : "/dashboard");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Sign-in failed");
    } finally {
      setIsLoading(false);
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

      <button
        type="button"
        onClick={handleLinkedInSignIn}
        disabled={isLoading}
        className="w-full rounded-lg bg-[#0A66C2] py-3 font-semibold text-paper-0 transition-colors hover:bg-[#094fa3] disabled:opacity-60"
      >
        {isLoading ? "Redirecting..." : "Continue with LinkedIn"}
      </button>

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
          <button
            type="submit"
            disabled={isLoading || !email.trim()}
            className="w-full rounded-lg border border-ink-200 bg-paper-0 py-3 font-semibold text-ink-900 transition-colors hover:bg-ink-50 disabled:opacity-60"
          >
            {isLoading ? "Sending…" : "Email me a login code"}
          </button>
        </form>
      ) : (
        <form onSubmit={handleVerifyCode} className="space-y-3">
          <Input
            type="text"
            inputMode="numeric"
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="6-digit code"
            autoComplete="one-time-code"
            required
          />
          <button
            type="submit"
            disabled={isLoading || otpCode.length < 6}
            className="w-full rounded-lg bg-ink-900 py-3 font-semibold text-paper-0 transition-colors hover:bg-ink-800 disabled:opacity-60"
          >
            {isLoading ? "Verifying…" : "Verify & continue"}
          </button>
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
        </form>
      )}

      <p className="text-xs text-ink-500 text-center">
        The same code signs you up or logs you in. We&apos;ll collect your experience via resume
        upload in onboarding.
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
            disabled={isLoading}
            className="w-full rounded-lg border border-ink-200 bg-paper-0 py-2.5 text-sm font-medium text-ink-900 hover:bg-ink-50 disabled:opacity-60"
          >
            {isLoading ? "Signing in…" : "Sign in with email (dev)"}
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
    message?.toLowerCase().includes("external provider") ||
    message?.toLowerCase().includes("user profile")
  ) {
    return (
      "LinkedIn sign-in failed at Supabase Auth. Check: (1) Supabase → Authentication → " +
      "Providers → LinkedIn (OIDC) is enabled with valid Client ID/Secret, " +
      "(2) LinkedIn app has “Sign In with LinkedIn using OpenID Connect” product, " +
      "(3) LinkedIn redirect URL is https://blwudfxurykzyutkqkoi.supabase.co/auth/v1/callback, " +
      "(4) Supabase redirect URLs include http://localhost:3001/auth/callback. " +
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
