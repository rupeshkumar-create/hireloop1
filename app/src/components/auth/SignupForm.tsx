"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { finishAuthSession } from "@/lib/auth/finish-auth-session";
import { resolvePostAuthDestination } from "@/lib/auth/post-auth-destination";
import { ApiUnreachableError, probeApiHealth } from "@/lib/api/auth-fetch";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { decodeAuthError } from "@/lib/auth/auth-errors";
import { verifyEmailCode } from "@/lib/auth/email-otp";
import {
  clearSignupRole,
  oauthCallbackUrl,
  persistSignupRole,
} from "@/lib/auth/signup-role-storage";
import {
  clearPostAuthRedirect,
  persistPostAuthRedirect,
  readPostAuthRedirect,
} from "@/lib/auth/post-auth-redirect";
import { cn } from "@/lib/utils";
import { Button, Input } from "@/components/ui";
import { BTN_CHIP, BTN_CHIP_ACTIVE, BTN_GHOST } from "@/lib/button-classes";

type Role = "candidate" | "recruiter";
type LoadingAction = "linkedin" | "email-send" | "email-verify" | "dev" | null;

const DEV_EMAIL_LOGIN = process.env.NEXT_PUBLIC_DEV_EMAIL_LOGIN === "true";

function formatAuthSetupError(error: unknown): string {
  if (error instanceof ApiUnreachableError) {
    return (
      "Your code was accepted, but we couldn't reach the Hireschema API to finish setup. " +
      "Check that the API is running and NEXT_PUBLIC_API_URL is set correctly, then try again."
    );
  }
  return error instanceof Error ? error.message : "Verification failed.";
}

export function SignupForm() {
  const supabase = useMemo(() => createClient(), []);
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
  /** Email the current OTP was issued for — verify against this, not a later edit. */
  const [otpEmail, setOtpEmail] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  // Sync locks: React state updates are too slow to stop double Enter / double-click
  // from issuing two OTPs (second email silently kills the first code).
  const otpInFlightRef = useRef(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const resendTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resendTimerRef.current !== null) {
        window.clearInterval(resendTimerRef.current);
      }
    };
  }, []);
  useEffect(() => {
    setRole(defaultRole);
    persistSignupRole(defaultRole);
  }, [defaultRole]);

  useEffect(() => {
    const returnTo = readPostAuthRedirect(searchParams);
    if (returnTo) persistPostAuthRedirect(returnTo);
  }, [searchParams]);

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
            hashDesc ? decodeURIComponent(hashDesc.replace(/\+/g, " ")) : null,
            "oauth",
          ),
        );
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      }
    }
  }, [searchParams]);

  async function routeAfterAuth(
    resolvedRole: string | undefined,
    isNewUser: boolean | undefined,
  ) {
    const savedRedirect = readPostAuthRedirect(searchParams);
    if (savedRedirect) {
      clearPostAuthRedirect();
      router.push(savedRedirect);
      return;
    }

    router.push(resolvePostAuthDestination(resolvedRole ?? role, Boolean(isNewUser)));
  }

  async function handleLinkedInSignIn() {
    setLoadingAction("linkedin");
    setErrorMessage("");
    setInfoMessage("");
    // Always overwrite sticky role so a prior Recruiter visit cannot hijack Job Seeker OAuth.
    persistSignupRole(role);

    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "linkedin_oidc",
        options: {
          // Embed signup_role in redirectTo (same idea as email OTP) so LinkedIn
          // cannot drop Job Seeker vs Recruiter intent after the OAuth round-trip.
          redirectTo: oauthCallbackUrl(role),
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
    const addr = email.trim().toLowerCase();
    if (!addr) return;
    // Sync lock: a double-fired send issues a second OTP that silently
    // invalidates the first — the classic "first code fails, second email works".
    if (otpInFlightRef.current || loadingAction !== null) return;
    otpInFlightRef.current = true;
    setLoadingAction("email-send");
    setErrorMessage("");
    setInfoMessage("");
    persistSignupRole(role);
    try {
      const redirectTo = `${window.location.origin}/auth/confirm?signup_role=${role}`;
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
      setEmail(addr);
      setOtpEmail(addr);
      setOtpCode("");
      setOtpSent(true);
      setInfoMessage("");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Couldn't send the code.");
    } finally {
      otpInFlightRef.current = false;
      setLoadingAction(null);
    }
  }

  function startResendCooldown() {
    if (resendTimerRef.current !== null) {
      window.clearInterval(resendTimerRef.current);
    }
    setResendCooldown(30);
    resendTimerRef.current = window.setInterval(() => {
      setResendCooldown((c) => {
        if (c <= 1) {
          if (resendTimerRef.current !== null) {
            window.clearInterval(resendTimerRef.current);
            resendTimerRef.current = null;
          }
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }

  async function handleResendCode() {
    const addr = (otpEmail || email).trim().toLowerCase();
    if (!addr || otpInFlightRef.current || loadingAction !== null || resendCooldown > 0) {
      return;
    }
    otpInFlightRef.current = true;
    setLoadingAction("email-send");
    setErrorMessage("");
    setOtpCode("");
    try {
      const redirectTo = `${window.location.origin}/auth/confirm?signup_role=${role}`;
      const { error } = await supabase.auth.signInWithOtp({
        email: addr,
        options: { shouldCreateUser: true, emailRedirectTo: redirectTo },
      });
      if (error) {
        setErrorMessage(error.message);
        return;
      }
      setOtpEmail(addr);
      setInfoMessage("New code sent — enter only this newest code (older codes no longer work).");
      startResendCooldown();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Couldn't resend the code.");
    } finally {
      otpInFlightRef.current = false;
      setLoadingAction(null);
    }
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault();
    const token = otpCode.trim();
    const addr = (otpEmail || email).trim().toLowerCase();
    if (token.length < 6 || !addr) return;
    if (otpInFlightRef.current || loadingAction !== null) return;
    otpInFlightRef.current = true;
    setLoadingAction("email-verify");
    setErrorMessage("");
    try {
      const { error: verifyError, accessToken } = await verifyEmailCode(
        supabase,
        addr,
        token,
      );
      if (verifyError || !accessToken) {
        if (verifyError) {
          const lowered = verifyError.toLowerCase();
          setErrorMessage(
            lowered.includes("invalid") || lowered.includes("expired")
              ? "That code is invalid or was already used. Tap Resend for a fresh code on this email — or use a different email. If you opened the email link, that code is spent; request a new email."
              : `${verifyError} Request a new code from signup if this keeps failing.`,
          );
        } else {
          setErrorMessage("Verified, but no session was created. Please try again.");
        }
        return;
      }
      const destination = await finishAuthSession(accessToken, role, {
        redirect: readPostAuthRedirect(searchParams),
      });
      clearSignupRole();
      clearPostAuthRedirect();
      router.replace(destination);
    } catch (error) {
      if (error instanceof ApiUnreachableError && typeof window !== "undefined") {
        const health = await probeApiHealth();
        if (health.ok) {
          setErrorMessage(
            "Your code was accepted, but account setup failed. Please try Verify & continue again.",
          );
          return;
        }
      }
      setErrorMessage(formatAuthSetupError(error));
    } finally {
      otpInFlightRef.current = false;
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
      persistSignupRole(role);
      const bootstrapRes = await fetch(`${getApiBaseUrl()}/api/v1/auth/bootstrap`, {
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

  const returnTo = readPostAuthRedirect(searchParams);
  const authToggleQs = new URLSearchParams();
  if (role === "recruiter") authToggleQs.set("role", "recruiter");
  if (!isSignIn) authToggleQs.set("mode", "signin");
  if (returnTo) authToggleQs.set("from", returnTo);
  const authToggleHref = `/signup${authToggleQs.toString() ? `?${authToggleQs}` : ""}`;

  return (
    <div className="space-y-6">
      {isSignIn && (
        <p className="text-small text-ink-600">
          Welcome back — sign in to continue where you left off.
        </p>
      )}
      <div className="space-y-2">
        <p className="text-sm font-medium text-ink-700">I am a…</p>
        <div className="grid grid-cols-2 gap-3">
          {(["candidate", "recruiter"] as Role[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => {
                setRole(r);
                persistSignupRole(r);
                // Keep the URL in sync so refresh/share and LinkedIn intent stay aligned.
                const next = new URLSearchParams(searchParams.toString());
                next.set("role", r);
                next.set("signup_role", r);
                router.replace(`/signup?${next.toString()}`, { scroll: false });
              }}
              className={cn(
                "p-3 text-sm",
                role === r ? BTN_CHIP_ACTIVE : BTN_CHIP,
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
        {loadingAction === "linkedin"
          ? "Redirecting..."
          : role === "candidate"
            ? "Continue with LinkedIn as Job Seeker"
            : "Continue with LinkedIn as Recruiter"}
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
            {loadingAction === "email-send" ? "Sending…" : "Email me a 6-digit code"}
          </Button>
        </form>
      ) : (
        <div className="space-y-3">
          <div className="rounded-lg border border-ink-100 bg-paper-1 p-4 text-center">
            <p className="text-small font-medium text-ink-900">Check your email</p>
            <p className="mt-1 text-xs text-ink-500 leading-relaxed">
              We sent a <strong>6-digit code</strong> to{" "}
              <span className="text-ink-800">{otpEmail || email}</span>. Enter it below —
              that&apos;s the most reliable path. Opening the email&apos;s sign-in link uses the
              same one-time login and will invalidate this code.
            </p>
            <p className="mt-2 text-[11px] text-ink-400 leading-relaxed">
              Code says invalid? Don&apos;t open the link — tap Resend for a fresh code, or try a
              different email. Only the newest code works.
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
              autoFocus
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
            onClick={() => void handleResendCode()}
            disabled={loadingAction !== null || resendCooldown > 0}
            className="w-full text-xs text-ink-600 hover:text-ink-900 disabled:opacity-50"
          >
            {resendCooldown > 0
              ? `Resend code in ${resendCooldown}s`
              : "Resend code (only the newest code works)"}
          </button>

          <button
            type="button"
            onClick={() => {
              if (otpInFlightRef.current) return;
              setOtpSent(false);
              setOtpEmail("");
              setOtpCode("");
              setInfoMessage("");
              setErrorMessage("");
              setResendCooldown(0);
              if (resendTimerRef.current !== null) {
                window.clearInterval(resendTimerRef.current);
                resendTimerRef.current = null;
              }
            }}
            className="w-full text-xs text-ink-500 hover:text-ink-900"
          >
            Use a different email
          </button>
        </div>
      )}

      <p className="text-xs text-ink-500 text-center">
        Prefer the email link? Use it <strong>or</strong> the code — not both. Resume upload
        happens in onboarding.
      </p>

      <p className="text-xs text-ink-500 text-center">
        {isSignIn ? (
          <>
            New to Hireschema?{" "}
            <Link href={authToggleHref} className="font-medium text-accent hover:underline">
              Create an account
            </Link>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <Link href={authToggleHref} className="font-medium text-accent hover:underline">
              Log in
            </Link>
          </>
        )}
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
            placeholder="priya.candidate@hireschema.com"
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
            className={cn(BTN_GHOST, "w-full py-2.5 text-sm disabled:opacity-60")}
          >
            {loadingAction === "dev" ? "Signing in…" : "Sign in with email (dev)"}
          </button>
          <p className="text-[11px] text-ink-500 leading-snug">
            Candidate password: <span className="font-mono">DemoCandidate26!</span>
            {" · "}
            Recruiter password: <span className="font-mono">DemoRecruiter26!</span>
          </p>
          <p className="text-[11px] text-ink-500 leading-snug">
            e.g. <span className="font-mono">priya.candidate@hireschema.com</span>
            {" · "}
            <span className="font-mono">arun.recruiter@hireschema.com</span>
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
