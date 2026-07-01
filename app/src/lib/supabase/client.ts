/**
 * Supabase browser client — use in Client Components only.
 * Uses the anon key (subject to RLS). Never use service key on the frontend.
 */
import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "@/types/database";
import { getSupabasePublicEnv } from "@/lib/supabase/env";

export function createClient() {
  const { url, anonKey } = getSupabasePublicEnv();
  return createBrowserClient<Database>(url, anonKey);
}
