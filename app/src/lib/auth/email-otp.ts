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

/** Try common Supabase email OTP types (signup vs returning sign-in).
 *
 * Order matters: our send path is signInWithOtp, whose codes verify with
 * type "email". Trying "signup" first guaranteed one failed attempt per
 * click — and GoTrue caps verification attempts per token, so a user who
 * retried a couple of times hit the cap and every later attempt reported
 * "invalid or expired" even with the correct code. "email" first means the
 * happy path costs exactly one attempt. */
export async function verifyEmailCode(
  supabase: BrowserSupabase,
  email: string,
  token: string,
): Promise<VerifyEmailResult> {
  const attempts = ["email", "signup", "magiclink"] as const;
  let lastError: string | null = null;

  for (const type of attempts) {
    try {
      const { data, error } = await withTimeout(
        supabase.auth.verifyOtp({ email, token, type }),
        VERIFY_OTP_TIMEOUT_MS,
        "Verification timed out. Check your connection and try again.",
      );
      if (!error) {
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
      }
      lastError = error.message;
    } catch (err) {
      lastError = err instanceof Error ? err.message : "Verification failed.";
      if (!lastError.toLowerCase().includes("timeout")) {
        continue;
      }
      return {
        error: lastError,
        accessToken: null,
      };
    }
  }

  return { error: lastError ?? "Invalid or expired code.", accessToken: null };
}
