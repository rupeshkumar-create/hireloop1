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

/** Try Supabase email OTP verification (signInWithOtp codes use type "email").

 * Do NOT cycle through signup/magiclink after an invalid/expired response —
 * GoTrue caps attempts per token and extra tries burn the code. */
export async function verifyEmailCode(
  supabase: BrowserSupabase,
  email: string,
  token: string,
): Promise<VerifyEmailResult> {
  try {
    const { data, error } = await withTimeout(
      supabase.auth.verifyOtp({ email, token, type: "email" }),
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

    const msg = error.message ?? "Invalid or expired code.";
    const lowered = msg.toLowerCase();
    if (lowered.includes("invalid") || lowered.includes("expired")) {
      return { error: msg, accessToken: null };
    }

    // Rare: wrong OTP type — try signup once (magic links use /auth/confirm, not this form).
    const fallback = await withTimeout(
      supabase.auth.verifyOtp({ email, token, type: "signup" }),
      VERIFY_OTP_TIMEOUT_MS,
      "Verification timed out. Check your connection and try again.",
    );
    if (!fallback.error) {
      const accessToken = fallback.data.session?.access_token ?? null;
      if (accessToken) {
        return { error: null, accessToken };
      }
    }

    return { error: fallback.error?.message ?? msg, accessToken: null };
  } catch (err) {
    const lastError = err instanceof Error ? err.message : "Verification failed.";
    return {
      error: lastError,
      accessToken: null,
    };
  }
}
