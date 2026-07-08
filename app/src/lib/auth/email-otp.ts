import { createClient } from "@/lib/supabase/client";

type BrowserSupabase = ReturnType<typeof createClient>;

export type VerifyEmailResult = {
  error: string | null;
  accessToken: string | null;
};

const VERIFY_OTP_TIMEOUT_MS = 20_000;

async function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error(message)), ms);
      }),
    ]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

/**
 * Verify a numeric email OTP from `signInWithOtp`.
 *
 * GoTrue uses type "email" for these codes. Never retry with signup/magiclink
 * after invalid/expired — each attempt burns the same one-time token, which is
 * why the first paste often fails and only a second email works.
 */
export async function verifyEmailCode(
  supabase: BrowserSupabase,
  email: string,
  token: string,
): Promise<VerifyEmailResult> {
  const normalizedEmail = email.trim().toLowerCase();
  const normalizedToken = token.trim();
  if (!normalizedEmail || normalizedToken.length < 6) {
    return { error: "Enter the full code from your email.", accessToken: null };
  }

  try {
    const { data, error } = await withTimeout(
      supabase.auth.verifyOtp({
        email: normalizedEmail,
        token: normalizedToken,
        type: "email",
      }),
      VERIFY_OTP_TIMEOUT_MS,
      "Verification timed out. Check your connection and try again.",
    );
    if (error) {
      return {
        error: error.message ?? "Invalid or expired code.",
        accessToken: null,
      };
    }

    const accessToken = data.session?.access_token ?? null;
    if (accessToken) {
      return { error: null, accessToken };
    }

    const { data: sessionData } = await withTimeout(
      supabase.auth.getSession(),
      5_000,
      "Session setup timed out. Please try again.",
    );
    if (sessionData.session?.access_token) {
      return { error: null, accessToken: sessionData.session.access_token };
    }

    return {
      error: "Verified, but no session was created. Please try again.",
      accessToken: null,
    };
  } catch (err) {
    const lastError = err instanceof Error ? err.message : "Verification failed.";
    return {
      error: lastError,
      accessToken: null,
    };
  }
}
