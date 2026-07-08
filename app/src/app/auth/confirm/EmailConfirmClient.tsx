"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { EmailOtpType } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";
import { finishAuthSession } from "@/lib/auth/finish-auth-session";
import { ApiUnreachableError } from "@/lib/api/auth-fetch";
import {
  clearPostAuthRedirect,
  readPostAuthRedirect,
} from "@/lib/auth/post-auth-redirect";
import {
  clearSignupRole,
  readSignupRole,
  signupUrl,
} from "@/lib/auth/signup-role-storage";
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
  const inFlightRef = useRef(false);

  async function handleConfirm() {
    // Sync lock — React state alone can still let double-clicks burn the token.
    if (inFlightRef.current || loading) return;
    inFlightRef.current = true;
    setLoading(true);
    setErrorMessage("");

    // Verify ONCE with the type from the email link. Cycling signup→email→magiclink
    // burns GoTrue attempt budget and can invalidate the same token the signup
    // form's 6-digit code uses.
    const { data, error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type,
    });

    if (error) {
      const lowered = (error.message ?? "").toLowerCase();
      setErrorMessage(
        lowered.includes("invalid") || lowered.includes("expired")
          ? "This link was already used or expired (some inboxes scan links automatically). Request a new email and enter the 6-digit code on the signup page — do not open the link if you plan to use the code."
          : error.message,
      );
      inFlightRef.current = false;
      setLoading(false);
      return;
    }

    let accessToken = data.session?.access_token ?? null;
    if (!accessToken) {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      accessToken = session?.access_token ?? null;
    }

    if (!accessToken) {
      setErrorMessage("Verified, but no session was created. Please try again from signup.");
      inFlightRef.current = false;
      setLoading(false);
      return;
    }

    const role = readSignupRole();

    try {
      const destination = await finishAuthSession(accessToken, role, {
        redirect: readPostAuthRedirect(),
      });
      clearSignupRole();
      clearPostAuthRedirect();
      router.replace(destination);
    } catch (err) {
      setErrorMessage(
        err instanceof ApiUnreachableError
          ? "Email verified, but we couldn't reach the Hireschema API to finish setup. Try again in a moment."
          : err instanceof Error
            ? err.message
            : "Account setup failed. Please try again.",
      );
      inFlightRef.current = false;
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper-0 px-6">
      <div className="w-full max-w-md space-y-6 rounded-xl border border-ink-100 bg-paper-1 p-8 text-center shadow-1">
        <div className="space-y-2">
          <h1 className="text-h2 text-ink-900">Confirm your email</h1>
          <p className="text-small text-ink-600 leading-relaxed">
            Tap continue to finish signing in to Hireschema. We wait for your click so automated
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
          {loading ? "Signing in…" : "Continue to Hireschema"}
        </Button>

        {errorMessage && (
          <div className="rounded-lg border border-destructive bg-destructive-bg p-3 text-left text-small text-destructive">
            {errorMessage}
          </div>
        )}

        <p className="text-xs text-ink-500 leading-relaxed">
          Prefer a code? Go to{" "}
          <a
            href={signupUrl(readSignupRole())}
            className="font-medium text-ink-800 hover:underline"
          >
            sign up
          </a>{" "}
          , request a <strong>fresh</strong> email, and enter the 6-digit code (same email&apos;s
          old link and code are one-time and cannot both be used).
        </p>
      </div>
    </main>
  );
}
