import { getServerApiBaseUrl } from "@/lib/api/base-url";

type ProfileOnboardingPayload = {
  candidate?: { onboarding_complete?: boolean };
};

/**
 * Single source of truth for onboarding_complete on server pages.
 * Prefer FastAPI /me/profile (same DB the wizard writes to); fall back to
 * Supabase only when the API token is missing or unreachable.
 */
export async function isOnboardingCompleteOnServer(opts: {
  token: string | undefined;
  supabaseFallback?: boolean | null;
  apiBase?: string;
}): Promise<boolean> {
  const apiBase = opts.apiBase ?? getServerApiBaseUrl();

  if (opts.token) {
    try {
      const res = await fetch(`${apiBase}/api/v1/me/profile`, {
        headers: { Authorization: `Bearer ${opts.token}` },
        cache: "no-store",
      });
      if (res.ok) {
        const data = (await res.json()) as ProfileOnboardingPayload;
        return data.candidate?.onboarding_complete === true;
      }
    } catch {
      /* fall through to Supabase */
    }
  }

  return opts.supabaseFallback === true;
}
