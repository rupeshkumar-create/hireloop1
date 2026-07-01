/**
 * Public Supabase env — shared by browser, server, and middleware clients.
 *
 * During `next build`, Preview deploys may not have env vars injected yet.
 * Placeholders let prerender complete; auth requires real values at runtime.
 */
export function getSupabasePublicEnv(): { url: string; anonKey: string } {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

  if (url && anonKey) {
    return { url, anonKey };
  }

  return {
    url: "https://placeholder.supabase.co",
    anonKey: "placeholder-anon-key",
  };
}
