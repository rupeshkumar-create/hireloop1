import type { User } from "@supabase/supabase-js";

const LINKEDIN_PROVIDERS = new Set(["linkedin", "linkedin_oidc"]);

export type SignupMethod = "linkedin" | "email";

/** How the user authenticated — drives onboarding copy (LinkedIn vs email OTP). */
export function resolveSignupMethod(user: User): SignupMethod {
  const appMeta = user.app_metadata ?? {};
  const provider = String(appMeta.provider ?? "").toLowerCase();
  if (LINKEDIN_PROVIDERS.has(provider)) {
    return "linkedin";
  }

  const providers = appMeta.providers;
  if (Array.isArray(providers)) {
    if (providers.some((p) => LINKEDIN_PROVIDERS.has(String(p).toLowerCase()))) {
      return "linkedin";
    }
  }

  const identities = user.identities ?? [];
  if (
    identities.some((identity) =>
      LINKEDIN_PROVIDERS.has(String(identity.provider ?? "").toLowerCase()),
    )
  ) {
    return "linkedin";
  }

  return "email";
}
