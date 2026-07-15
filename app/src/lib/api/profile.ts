import { apiFetch } from "@/lib/api/client";
import { apiAuthFetch } from "@/lib/api/auth-fetch";

export type DisplayCurrency = "auto" | "INR" | "USD" | "GBP" | "EUR";

export type MyProfileData = {
  user: {
    id: string;
    email: string;
    phone: string | null;
    full_name: string | null;
    role?: string;
    phone_verified?: boolean;
    market?: string;
    avatar_url?: string | null;
    /** True for DB admins AND founders in SUPER_ADMIN_EMAILS — gates the Admin link. */
    is_admin?: boolean;
  } | null;
  candidate: {
    id: string;
    headline: string | null;
    summary: string | null;
    current_title: string | null;
    current_company: string | null;
    years_experience: number | null;
    location_city: string | null;
    location_state: string | null;
    skills: string[] | null;
    profile_complete: boolean;
    onboarding_complete?: boolean;
    visibility?: CandidateVisibility;
    looking_for?: string | null;
    remote_preference?: RemotePreference;
    open_to_relocation?: boolean;
    location_scope?: LocationScope;
    expected_ctc_min?: number | null;
    expected_ctc_max?: number | null;
    current_ctc?: number | null;
    notice_period_days?: number | null;
    is_active?: boolean;
    linkedin_url?: string | null;
    display_currency?: DisplayCurrency;
    display_currency_resolved?: string;
    public_slug?: string | null;
    public_profile_enabled?: boolean;
    public_profile_url?: string | null;
    hide_contact_public?: boolean;
    share_with_recruiters?: boolean;
    /** Opt-in for per-job and per-path AI tailored resumes (default off). */
    tailored_resume_enabled?: boolean;
  } | null;
  experience?: WorkExperience[];
  education?: Education[];
  resume_filename?: string | null;
};

export type WorkExperience = {
  company?: string | null;
  title?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
  is_current?: boolean;
  location?: string | null;
  industry?: string | null;
  employment_type?: string | null;
  seniority?: string | null;
  source?: "linkedin" | "resume" | "career_profile" | "profile" | string;
  aarya_insights?: string[];
};

export type Education = {
  institution?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  grade?: string | null;
  /** Which source this entry was merged from (LinkedIn / resume / career_profile). */
  source?: "linkedin" | "resume" | "career_profile" | string;
};

export type CandidateVisibility =
  | "open_to_matches"
  | "exceptional_only"
  | "private";

/** How job feeds and Aarya filter remote vs on-site roles. */
export type RemotePreference = "any" | "remote_only" | "onsite_only";
export type LocationScope = "city" | "state" | "country" | "global";

export const REMOTE_PREFERENCE_OPTIONS: {
  id: RemotePreference;
  label: string;
  hint: string;
}[] = [
  {
    id: "any",
    label: "Remote & on-site",
    hint: "Show all matching roles, including fully remote.",
  },
  {
    id: "remote_only",
    label: "Remote only",
    hint: "Only WFH / fully remote listings.",
  },
  {
    id: "onsite_only",
    label: "On-site only",
    hint: "Exclude fully remote roles — office or hybrid in a city.",
  },
];

export async function updateRemotePreference(
  remotePreference: RemotePreference
): Promise<void> {
  await apiFetch("/api/v1/me/profile", {
    method: "PATCH",
    body: JSON.stringify({ remote_preference: remotePreference }),
  });
}

export async function updateProfileVisibility(
  visibility: CandidateVisibility
): Promise<void> {
  await apiFetch("/api/v1/me/profile", {
    method: "PATCH",
    body: JSON.stringify({ visibility }),
  });
}

/** Fields the profile-completion form can write. All optional — send a subset. */
export type ProfilePatch = {
  current_title?: string;
  current_company?: string;
  years_experience?: number;
  skills?: string[];
  location_city?: string;
  location_state?: string;
  remote_preference?: RemotePreference;
  open_to_relocation?: boolean;
  location_scope?: LocationScope;
  expected_ctc_min?: number;
  expected_ctc_max?: number;
  current_ctc?: number;
  notice_period_days?: number;
  looking_for?: string;
  summary?: string;
  visibility?: CandidateVisibility;
  display_currency?: DisplayCurrency;
  public_profile_enabled?: boolean;
  hide_contact_public?: boolean;
  share_with_recruiters?: boolean;
  tailored_resume_enabled?: boolean;
};

/** Generic profile PATCH. Invalidates the local profile cache on success. */
export async function updateMyProfile(patch: ProfilePatch): Promise<void> {
  await apiFetch("/api/v1/me/profile", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  invalidateProfileCache();
}

export async function publishPublicProfile(): Promise<{
  slug: string;
  public_profile_url: string;
}> {
  const data = await apiFetch<{ slug: string; public_profile_url: string }>(
    "/api/v1/me/public-profile/publish",
    { method: "POST" }
  );
  invalidateProfileCache();
  return data;
}

export async function updateMyMarket(market: string): Promise<void> {
  await apiFetch("/api/v1/me/market", {
    method: "PATCH",
    body: JSON.stringify({ market }),
  });
  invalidateProfileCache();
}

/** Infer market from CDN geo headers (Vercel / Cloudflare). Best-effort, silent. */
export async function inferMarketFromGeo(): Promise<string | null> {
  try {
    const data = await apiFetch<{ ok: boolean; market: string | null; updated?: boolean }>(
      "/api/v1/me/market/from-geo",
      { method: "POST" },
    );
    if (data.ok && data.market) {
      invalidateProfileCache();
      return data.market;
    }
  } catch {
    /* geo headers may be absent in local dev */
  }
  return null;
}

// ── In-memory profile cache ─────────────────────────────────────────────────
//
// The Profile panel fully remounts every time it's opened (the dashboard keys
// panels by id), and the chat empty-state also reads the profile. Without a
// cache that means a fresh /me/profile round-trip — and a loading spinner —
// every single time. We keep the last successful payload in module scope so
// reopening is instant, and we de-dupe concurrent in-flight requests so two
// callers mounting at once share one network call.

let _profileCache: MyProfileData | null = null;
let _profileInFlight: Promise<MyProfileData> | null = null;

/** Last successfully fetched profile, or null if none cached yet. Synchronous. */
export function getCachedProfile(): MyProfileData | null {
  return _profileCache;
}

/** Drop the cache — call after a profile mutation so the next read revalidates. */
export function invalidateProfileCache(): void {
  _profileCache = null;
}

/**
 * Fetch the current user's profile.
 *
 * @param opts.force  Bypass the in-flight de-dupe and force a fresh request
 *                    (the result still refreshes the cache).
 */
export async function fetchMyProfile(
  opts: { force?: boolean } = {}
): Promise<MyProfileData> {
  if (opts.force) {
    _profileCache = null;
    _profileInFlight = null;
  } else if (_profileInFlight) {
    return _profileInFlight;
  }

  const req = apiFetch<MyProfileData>("/api/v1/me/profile")
    .then((data) => {
      _profileCache = data;
      return data;
    })
    .finally(() => {
      if (_profileInFlight === req) _profileInFlight = null;
    });

  _profileInFlight = req;
  return req;
}

export function applyProfileToForm(
  data: MyProfileData,
  setters: {
    setProfile: (p: MyProfileData) => void;
    setFullName: (v: string) => void;
    setHeadline: (v: string) => void;
    setCurrentTitle: (v: string) => void;
    setSummary?: (v: string) => void;
    setCurrentCompany?: (v: string) => void;
    setLocationCity?: (v: string) => void;
    setLocationState?: (v: string) => void;
    setLookingFor?: (v: string) => void;
  }
) {
  setters.setProfile(data);
  setters.setFullName(data.user?.full_name ?? "");
  const headline = data.candidate?.headline;
  const fallbackTitle = data.candidate?.current_title;
  setters.setHeadline(
    headline && headline !== "New candidate"
      ? headline
      : fallbackTitle ?? headline ?? "",
  );
  setters.setCurrentTitle(data.candidate?.current_title ?? "");
  setters.setSummary?.(data.candidate?.summary ?? "");
  setters.setCurrentCompany?.(data.candidate?.current_company ?? "");
  setters.setLocationCity?.(data.candidate?.location_city ?? "");
  setters.setLocationState?.(data.candidate?.location_state ?? "");
  setters.setLookingFor?.(data.candidate?.looking_for ?? "");
}

/** Authenticated DPDP export download (Bearer required — bare window.open 401s). */
export async function downloadDpdpExport(): Promise<void> {
  const res = await apiAuthFetch("/api/v1/me/dpdp/export");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Export failed: ${res.status}`,
    );
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `hireschema-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
