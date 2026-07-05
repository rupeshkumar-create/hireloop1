import type { User } from "@supabase/supabase-js";

function cleanName(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/** Display name from Supabase Auth (LinkedIn OIDC user_metadata / identities). */
export function displayNameFromSupabaseUser(
  user: User | null | undefined,
): string | undefined {
  if (!user) return undefined;

  const meta = user.user_metadata ?? {};
  const fromMeta =
    cleanName(meta.full_name) ??
    cleanName(meta.name) ??
    cleanName(meta.preferred_username);
  if (fromMeta) return fromMeta;

  const given = cleanName(meta.given_name);
  if (given) {
    const family = cleanName(meta.family_name);
    return family ? `${given} ${family}` : given;
  }

  for (const identity of user.identities ?? []) {
    const data = identity.identity_data ?? {};
    const fromIdentity =
      cleanName(data.full_name) ??
      cleanName(data.name) ??
      cleanName(data.given_name);
    if (fromIdentity) return fromIdentity;
    const idGiven = cleanName(data.given_name);
    if (idGiven) {
      const idFamily = cleanName(data.family_name);
      return idFamily ? `${idGiven} ${idFamily}` : idGiven;
    }
  }

  const email = user.email?.trim();
  if (email && !email.endsWith("@signup.hireloop.internal")) {
    const local = email.split("@")[0]?.trim();
    if (local) return local;
  }

  return undefined;
}

export function firstNameFromDisplayName(name: string | undefined): string | undefined {
  const trimmed = name?.trim();
  if (!trimmed) return undefined;
  return trimmed.split(/\s+/)[0];
}
