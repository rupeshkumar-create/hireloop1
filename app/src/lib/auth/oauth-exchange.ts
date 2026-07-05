import { createClient } from "@/lib/supabase/client";

const EXCHANGE_LOCK_PREFIX = "hireloop_oauth_exchange:";

type BrowserSupabase = ReturnType<typeof createClient>;

/**
 * Exchange a one-time OAuth `code` for a session exactly once per page load.
 * Guards against React strict-mode double effects and duplicate client calls.
 */
export async function exchangeOAuthCodeOnce(
  supabase: BrowserSupabase,
  code: string,
): Promise<{ error: Error | null }> {
  const lockKey = `${EXCHANGE_LOCK_PREFIX}${code}`;
  if (typeof window !== "undefined") {
    if (sessionStorage.getItem(lockKey) === "done") {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      return session?.access_token
        ? { error: null }
        : { error: new Error("OAuth session missing after exchange.") };
    }
    if (sessionStorage.getItem(lockKey) === "pending") {
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 100));
        if (sessionStorage.getItem(lockKey) === "done") {
          const {
            data: { session },
          } = await supabase.auth.getSession();
          return session?.access_token
            ? { error: null }
            : { error: new Error("OAuth session missing after exchange.") };
        }
        if (sessionStorage.getItem(lockKey) !== "pending") break;
      }
    }
    sessionStorage.setItem(lockKey, "pending");
  }

  const {
    data: { session: existing },
  } = await supabase.auth.getSession();
  if (existing?.access_token) {
    if (typeof window !== "undefined") {
      sessionStorage.setItem(lockKey, "done");
    }
    return { error: null };
  }

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (!error && typeof window !== "undefined") {
    sessionStorage.setItem(lockKey, "done");
  } else if (error && typeof window !== "undefined") {
    sessionStorage.removeItem(lockKey);
  }
  return { error: error ? new Error(error.message) : null };
}
