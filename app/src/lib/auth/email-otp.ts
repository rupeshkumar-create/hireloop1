import { createClient } from "@/lib/supabase/client";

type BrowserSupabase = ReturnType<typeof createClient>;

/** Try common Supabase email OTP types (signup vs returning sign-in). */
export async function verifyEmailCode(
  supabase: BrowserSupabase,
  email: string,
  token: string,
): Promise<string | null> {
  const attempts = ["signup", "email", "magiclink"] as const;
  let lastError: string | null = null;
  for (const type of attempts) {
    const { error } = await supabase.auth.verifyOtp({
      email,
      token,
      type,
    });
    if (!error) return null;
    lastError = error.message;
  }
  return lastError ?? "Invalid or expired code.";
}
