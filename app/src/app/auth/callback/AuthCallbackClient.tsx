"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { finishAuthSession } from "@/lib/auth/finish-auth-session";
import { exchangeOAuthCodeOnce } from "@/lib/auth/oauth-exchange";
import { decodeAuthError } from "@/lib/auth/auth-errors";
import {
  clearPostAuthRedirect,
  readPostAuthRedirect,
} from "@/lib/auth/post-auth-redirect";
import {
  clearSignupRole,
  readSignupRole,
  signupUrl,
} from "@/lib/auth/signup-role-storage";
import { ApiUnreachableError } from "@/lib/api/auth-fetch";

/**
 * LinkedIn OAuth callback — exchange the auth code in the browser so the PKCE
 * code_verifier cookie (set when the user clicked “Continue with LinkedIn”) is
 * available. Email magic links use /auth/confirm instead; they never land here.
 */
export function AuthCallbackClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const supabase = createClient();
  const started = useRef(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [errorRole, setErrorRole] = useState<"candidate" | "recruiter">("candidate");

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const role = readSignupRole(searchParams);

    const oauthError = searchParams.get("error");
    const oauthErrorDescription = searchParams.get("error_description");
    if (oauthError) {
      const message = oauthErrorDescription
        ? decodeURIComponent(oauthErrorDescription.replace(/\+/g, " "))
        : null;
      router.replace(
        signupUrl(role, {
          error: oauthError,
          message: decodeAuthError(oauthError, message, "oauth"),
        }),
      );
      return;
    }

    const tokenHash = searchParams.get("token_hash");
    if (tokenHash) {
      const confirm = new URL("/auth/confirm", window.location.origin);
      confirm.searchParams.set("token_hash", tokenHash);
      const tokenType = searchParams.get("type");
      if (tokenType) confirm.searchParams.set("type", tokenType);
      router.replace(`${confirm.pathname}${confirm.search}`);
      return;
    }

    const code = searchParams.get("code");
    if (!code) {
      router.replace(
        signupUrl(role, {
          error: "auth_failed",
          message:
            "LinkedIn sign-in link is incomplete or expired. Tap Continue with LinkedIn again.",
        }),
      );
      return;
    }

    const explicitNext = searchParams.get("next");

    void (async () => {
      const { error: exchangeError } = await exchangeOAuthCodeOnce(supabase, code);
      if (exchangeError) {
        const {
          data: { session: recovered },
        } = await supabase.auth.getSession();
        if (!recovered?.access_token) {
          setErrorRole(role);
          setErrorMessage(decodeAuthError("auth_failed", exchangeError.message, "oauth"));
          return;
        }
      }

      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        setErrorRole(role);
        setErrorMessage("LinkedIn sign-in completed but no session was created. Please try again.");
        return;
      }

      let destination = role === "recruiter" ? "/recruiter/onboarding" : "/onboarding";
      try {
        destination = await finishAuthSession(session.access_token, role, {
          redirect: readPostAuthRedirect(searchParams),
        });
      } catch (err) {
        const message =
          err instanceof ApiUnreachableError
            ? "LinkedIn sign-in succeeded, but we couldn't reach the Hireschema API to finish setup. Try again in a moment."
            : err instanceof Error
              ? err.message
              : "Account setup failed. Please try signing in again.";
        router.replace(
          signupUrl(role, { error: "bootstrap_failed", message }),
        );
        return;
      }

      clearSignupRole();
      clearPostAuthRedirect();

      const isRealDeepLink =
        !!explicitNext && explicitNext.startsWith("/") && explicitNext !== "/onboarding";
      router.replace(isRealDeepLink ? explicitNext : destination);
    })();
  }, [router, searchParams, supabase]);

  if (errorMessage) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-paper-0 px-6">
        <div className="w-full max-w-md space-y-4 rounded-xl border border-ink-100 bg-paper-1 p-8 text-center shadow-1">
          <h1 className="text-h2 text-ink-900">LinkedIn sign-in failed</h1>
          <p className="text-small text-ink-600">{errorMessage}</p>
          <a
            href={signupUrl(errorRole)}
            className="inline-block text-small font-medium text-accent hover:underline"
          >
            Back to sign up
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-paper-0 px-6">
      <div className="text-center space-y-2">
        <p className="text-body text-ink-900">Finishing LinkedIn sign-in…</p>
        <p className="text-small text-ink-500">This only takes a moment.</p>
      </div>
    </main>
  );
}
