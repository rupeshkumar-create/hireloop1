"use client";

/**
 * Settings page — profile, notifications, privacy, account.
 *
 * Notification categories are defined CLIENT-SIDE so they always render with
 * proper human-readable labels. The API stores toggle state keyed by category id;
 * we never iterate over raw API keys to derive the category list.
 */

import { useEffect, useState } from "react";
import { LogOut, Shield } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/client";
import {
  applyProfileToForm,
  fetchMyProfile,
  type MyProfileData,
} from "@/lib/api/profile";
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  useToast,
} from "@/components/ui";
import { AppShell } from "@/components/layout/AppShell";
import { cn } from "@/lib/utils";

// ── Notification categories ────────────────────────────────────────────────────
// IMPORTANT: the list is defined here — never derived from Object.keys(apiResponse).
// The API only stores toggle state; the labels live in this file.

type NotifCat = { id: string; label: string; desc: string };

const NOTIFICATION_CATEGORIES: NotifCat[] = [
  {
    id:    "job_match_alerts",
    label: "Job match alerts",
    desc:  "New jobs matching your profile",
  },
  {
    id:    "intro_updates",
    label: "Intro request updates",
    desc:  "When a recruiter responds to your intro",
  },
  {
    id:    "interview_reminders",
    label: "Interview reminders",
    desc:  "Upcoming scheduled interviews",
  },
  {
    id:    "aarya_digest",
    label: "Weekly digest",
    desc:  "Your career progress summary from Aarya",
  },
  {
    id:    "profile_views",
    label: "Profile viewed",
    desc:  "When recruiters view your profile",
  },
  {
    id:    "application_updates",
    label: "Application updates",
    desc:  "Status changes on your applications",
  },
  {
    id:    "platform_updates",
    label: "Platform updates",
    desc:  "New Hireloop features and improvements",
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { toast } = useToast();

  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await createClient().auth.signOut();
    } catch {
      // Fall through — the hard redirect lands on /login regardless.
    } finally {
      window.location.href = "/login";
    }
  }

  // Profile state
  const [profile,       setProfile]       = useState<MyProfileData | null>(null);
  const [fullName,      setFullName]       = useState("");
  const [headline,      setHeadline]       = useState("");
  const [currentTitle,  setCurrentTitle]   = useState("");
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [profileError,  setProfileError]  = useState("");
  const [savingProfile, setSavingProfile]  = useState(false);

  // Notification prefs state — keyed by category id, value = { whatsapp: bool }
  const [prefs,       setPrefs]       = useState<Record<string, Record<string, boolean>>>({});
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoadingProfile(true);
      setProfileError("");
      try {
        const d = await fetchMyProfile();
        applyProfileToForm(d, {
          setProfile,
          setFullName,
          setHeadline,
          setCurrentTitle,
        });
      } catch (err) {
        setProfileError(
          err instanceof Error ? err.message : "Couldn't load profile"
        );
      } finally {
        setLoadingProfile(false);
      }
    };
    void load();

    apiFetch<{ prefs: Record<string, Record<string, boolean>> }>(
      "/api/v1/me/notification-prefs"
    )
      .then((d) => setPrefs(d.prefs ?? {}))
      .catch(() => {});
  }, []);

  async function saveProfile() {
    setSavingProfile(true);
    try {
      await apiFetch("/api/v1/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name:     fullName.trim() || undefined,
          headline:      headline.trim() || undefined,
          current_title: currentTitle.trim() || undefined,
        }),
      });
      const refreshed = await fetchMyProfile();
      applyProfileToForm(refreshed, {
        setProfile,
        setFullName,
        setHeadline,
        setCurrentTitle,
      });
      setProfileError("");
      toast.success("Profile updated");
    } catch {
      toast.error("Couldn't update profile");
    } finally {
      setSavingProfile(false);
    }
  }

  async function savePrefs() {
    setSavingPrefs(true);
    try {
      await apiFetch("/api/v1/me/notification-prefs", {
        method: "PATCH",
        body: JSON.stringify({ prefs }),
      });
      toast.success("Notification preferences saved");
    } catch {
      toast.error("Couldn't save preferences");
    } finally {
      setSavingPrefs(false);
    }
  }

  function setToggle(catId: string, checked: boolean) {
    setPrefs((p) => ({
      ...p,
      [catId]: { ...(p[catId] ?? {}), whatsapp: checked },
    }));
  }

  async function deleteAccount() {
    if (!confirm("Delete your account? Your data will be purged after 30 days.")) return;
    try {
      await apiFetch("/api/v1/me", { method: "DELETE" });
      toast.success("Account deletion scheduled. Data purged after 30 days.");
    } catch {
      toast.error("Couldn't schedule deletion. Contact support@hireloop.in");
    }
  }

  const inputClass =
    "w-full px-3 py-2 rounded-md border border-ink-200 bg-paper-0 text-small text-ink-900 " +
    "placeholder:text-ink-400 focus:outline-none focus:ring-1 focus:ring-ink-900 transition-shadow";

  return (
    <AppShell title="Settings">
      <div className="space-y-4">

        {/* Profile */}
        <Card>
          <CardHeader
            title="My profile"
            description={
              profile?.user?.email ?? (loadingProfile ? "Loading…" : undefined)
            }
          />
          <CardBody className="space-y-3 !pt-0">
            {profileError && (
              <p className="text-small text-destructive">{profileError}</p>
            )}
            {profile?.user?.phone && (
              <p className="text-small text-ink-600">
                Phone: <span className="text-ink-900">{profile.user.phone}</span>
              </p>
            )}
            <label className="block space-y-1">
              <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                Full name
              </span>
              <input
                className={inputClass}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your full name"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                Headline
              </span>
              <input
                className={inputClass}
                value={headline}
                onChange={(e) => setHeadline(e.target.value)}
                placeholder="e.g. Senior Software Engineer"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                Current role
              </span>
              <input
                className={inputClass}
                value={currentTitle}
                onChange={(e) => setCurrentTitle(e.target.value)}
                placeholder="e.g. Software Engineer at Google"
              />
            </label>

            {profile?.candidate?.skills && profile.candidate.skills.length > 0 && (
              <div className="space-y-1.5 pt-1">
                <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                  Skills
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {profile.candidate.skills.slice(0, 15).map((s) => (
                    <span
                      key={s}
                      className="px-2 py-0.5 rounded-full bg-ink-100 text-micro text-ink-700 font-medium"
                    >
                      {s}
                    </span>
                  ))}
                  {profile.candidate.skills.length > 15 && (
                    <span className="px-2 py-0.5 rounded-full bg-ink-100 text-micro text-ink-500">
                      +{profile.candidate.skills.length - 15} more
                    </span>
                  )}
                </div>
                <p className="text-micro text-ink-400 pt-0.5">
                  Skills are updated automatically when you upload a resume or complete a voice session.
                </p>
              </div>
            )}

            {profile?.candidate?.location_city && (
              <p className="text-micro text-ink-500">
                Location: {profile.candidate.location_city}
                {profile.candidate.location_state && `, ${profile.candidate.location_state}`}
              </p>
            )}

            {profile?.candidate?.years_experience != null && (
              <p className="text-micro text-ink-500">
                Experience: {profile.candidate.years_experience} year
                {profile.candidate.years_experience !== 1 ? "s" : ""}
              </p>
            )}
          </CardBody>
          <CardFooter>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void saveProfile()}
              loading={savingProfile}
            >
              Save profile
            </Button>
          </CardFooter>
        </Card>

        {/* Notifications */}
        <Card>
          <CardHeader
            title="Notifications"
            description="Choose how Aarya reaches you when matches or intros change."
          />
          <CardBody className="space-y-0.5 !pt-0">
            {NOTIFICATION_CATEGORIES.map((cat) => (
              <div
                key={cat.id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div className="min-w-0">
                  <p className="text-small font-medium text-ink-900">{cat.label}</p>
                  <p className="text-micro text-ink-500">{cat.desc}</p>
                </div>
                <Toggle
                  checked={prefs[cat.id]?.whatsapp ?? true}
                  onChange={(v) => setToggle(cat.id, v)}
                />
              </div>
            ))}
          </CardBody>
          <CardFooter>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void savePrefs()}
              loading={savingPrefs}
            >
              Save preferences
            </Button>
          </CardFooter>
        </Card>

        {/* Privacy */}
        <Card>
          <CardHeader
            title="Privacy"
            description="Your data, on your terms. DPDP Act 2023 compliant."
          />
          <CardBody className="space-y-2 !pt-0">
            <p className="text-small text-ink-500">
              Data Protection Officer: privacy@hireloop.in
            </p>
            <div className="flex flex-col gap-2 pt-1">
              <button
                onClick={() =>
                  window.open(
                    `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/me/dpdp/export`,
                    "_blank"
                  )
                }
                className="flex items-center gap-2.5 rounded-md border border-ink-200 px-4 py-2.5 text-small text-ink-700 hover:bg-ink-50 transition-colors text-left"
              >
                <Shield className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
                Export my data (JSON)
              </button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => void deleteAccount()}
                fullWidth
              >
                Delete my account
              </Button>
            </div>
          </CardBody>
        </Card>

        {/* Account */}
        <Card>
          <CardHeader title="Account" />
          <CardBody className="!pt-0">
            <button
              onClick={() => void handleSignOut()}
              disabled={signingOut}
              className="w-full flex items-center gap-2.5 rounded-md border border-ink-200 px-4 py-2.5 text-small text-ink-700 hover:bg-ink-50 transition-colors text-left disabled:opacity-50"
            >
              <LogOut className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </CardBody>
        </Card>
      </div>
    </AppShell>
  );
}

// ── Toggle switch ─────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-5 w-9 rounded-full transition-colors duration-fast ease-out-soft shrink-0",
        checked ? "bg-accent" : "bg-ink-100"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-paper-1 shadow-1 transition-transform duration-fast",
          checked ? "translate-x-[18px]" : "translate-x-0.5"
        )}
      />
    </button>
  );
}
