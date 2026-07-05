"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { EmailOtpType } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";
import { SIGNUP_ROLE_COOKIE } from "@/lib/auth/constants";
import { finishAuthSession } from "@/lib/auth/finish-auth-session";
import { ApiUnreachableError } from "@/lib/api/auth-fetch";
import { Button } from "@/components/ui";

type EmailConfirmClientProps = {
  tokenHash: string;
  type: EmailOtpType;
};

export function EmailConfirmClient({ tokenHash, type }: EmailConfirmClientProps) {
  const router = useRouter();
  const supabase = createClient();
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  async function handleConfirm() {
    setLoading(true);
    setErrorMessage("");

    const attempts: EmailOtpType[] = ["signup", "email", "magiclink", type].filter(
      (value, index, arr) => arr.indexOf(value) === index,
    );

    let lastError: string | null = null;
    for (const attemptType of attempts) {
      const { error } = await supabase.auth.verifyOtp({
        token_hash: tokenHash,
        type: attemptType,
      });
      if (!error) {
        lastError = null;
        break;
      }
      lastError = error.message;
    }

    if (lastError) {
      const lowered = lastError.toLowerCase();
      setErrorMessage(
        lowered.includes("invalid") || lowered.includes("expired")
          ? "This link was already used or expired (temp-mail scanners often open links before you do). Request a new email and use the 6-digit code on the signup page instead."
          : lastError,
      );
      setLoading(false);
      return;
    }

    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session?.access_token) {
      setErrorMessage("Verified, but no session was created. Please try again from signup.");
      setLoading(false);
      return;
    }

    const roleCookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith(`${SIGNUP_ROLE_COOKIE}=`))
      ?.split("=")[1];
    const role = roleCookie === "recruiter" ? "recruiter" : "candidate";

    try {
      const destination = await finishAuthSession(session.access_token, role);
      document.cookie = `${SIGNUP_ROLE_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
      router.replace(destination);
    } catch (err) {
      setErrorMessage(
        err instanceof ApiUnreachableError
          ? "Email verified, but we couldn't reach the Hireloop API to finish setup. Try again in a moment."
          : err instanceof Error
            ? err.message
            : "Account setup failed. Please try again.",
      );
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper-0 px-6">
      <div className="w-full max-w-md space-y-6 rounded-xl border border-ink-100 bg-paper-1 p-8 text-center shadow-1">
        <div className="space-y-2">
          <h1 className="text-h2 text-ink-900">Confirm your email</h1>
          <p className="text-small text-ink-600 leading-relaxed">
            Tap continue to finish signing in to Hireloop. We wait for your click so automated
            email scanners don&apos;t burn your link before you open it.
          </p>
        </div>

        <Button
          type="button"
          variant="primary"
          size="lg"
          fullWidth
          loading={loading}
          onClick={() => void handleConfirm()}
          className="rounded-lg font-semibold"
        >
          {loading ? "Signing in…" : "Continue to Hireloop"}
        </Button>

        {errorMessage && (
          <div className="rounded-lg border border-destructive bg-destructive-bg p-3 text-left text-small text-destructive">
            {errorMessage}
          </div>
        )}

        <p className="text-xs text-ink-500 leading-relaxed">
          Prefer a code? Go to{" "}
          <a href="/signup" className="font-medium text-ink-800 hover:underline">
            sign up
          </a>{" "}
          and enter the 6-digit code from the same email.
        </p>
      </div>
    </main>
  );
}
