"use client";

import { useEffect, useState } from "react";
import { LogOut, Shield, User } from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import { fetchMyProfile, downloadDpdpExport, type MyProfileData } from "@/lib/api/profile";
import { CandidateSharingSettings } from "@/components/settings/CandidateSharingSettings";
import { RoleSwitchButton } from "@/components/layout/RoleSwitchButton";
import { TailoredResumeSettings } from "@/components/settings/TailoredResumeSettings";
import { NOTIFICATION_CATEGORIES } from "@/lib/notification-categories";
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  useToast,
} from "@/components/ui";
import { cn } from "@/lib/utils";
import { BTN_ROW } from "@/lib/button-classes";

export type SettingsPanelProps = {
  onEditProfile?: () => void;
  onSignOut?: () => void;
  signingOut?: boolean;
};

export function SettingsPanel({
  onEditProfile,
  onSignOut,
  signingOut = false,
}: SettingsPanelProps) {
  const { toast } = useToast();

  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [profileError, setProfileError] = useState("");
  const [prefs, setPrefs] = useState<Record<string, Record<string, boolean>>>({});
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoadingProfile(true);
      setProfileError("");
      try {
        const d = await fetchMyProfile();
        setProfile(d);
      } catch (err) {
        setProfileError(err instanceof Error ? err.message : "Couldn't load profile");
      } finally {
        setLoadingProfile(false);
      }
    };
    void load();

    apiFetch<{ prefs: Record<string, Record<string, boolean>> }>(
      "/api/v1/me/notification-prefs",
    )
      .then((d) => setPrefs(d.prefs ?? {}))
      .catch(() => {});
  }, []);

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
      [catId]: { ...(p[catId] ?? {}), email: checked },
    }));
  }

  async function exportMyData() {
    try {
      await downloadDpdpExport();
      toast.success("Data export downloaded");
    } catch {
      toast.error("Couldn't export your data. Try again or contact privacy@hireschema.com");
    }
  }

  async function deleteAccount() {
    if (!confirm("Delete your account? Your data will be purged after 30 days.")) return;
    try {
      await apiFetch("/api/v1/me", { method: "DELETE" });
      toast.success("Account deletion scheduled. Data purged after 30 days.");
    } catch {
      toast.error("Couldn't schedule deletion. Contact support@hireschema.com");
    }
  }

  const displayName =
    profile?.user?.full_name?.trim() ||
    profile?.candidate?.headline?.trim() ||
    "Your profile";

  const avatarUrl = profile?.user?.avatar_url?.trim() || null;
  const initials = displayName
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="p-5 space-y-4">
      <Card>
        <CardHeader
          title="Career profile"
          description="Headline, experience, resume, and career story"
        />
        <CardBody className="space-y-3 !pt-0">
          {profileError && <p className="text-small text-destructive">{profileError}</p>}
          {loadingProfile ? (
            <p className="text-small text-ink-500">Loading…</p>
          ) : (
            <>
              <div className="flex items-center gap-3">
                {avatarUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={avatarUrl}
                    alt={displayName}
                    className="w-10 h-10 rounded-full object-cover shrink-0"
                  />
                ) : (
                  <div className="w-10 h-10 rounded-full bg-ink-100 flex items-center justify-center shrink-0">
                    {initials ? (
                      <span className="text-micro font-semibold text-ink-600">{initials}</span>
                    ) : (
                      <User className="h-5 w-5 text-ink-500" strokeWidth={1.5} />
                    )}
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-small font-medium text-ink-900 truncate">{displayName}</p>
                  <p className="text-micro text-ink-500 truncate">
                    {profile?.user?.email ?? "—"}
                  </p>
                </div>
              </div>
              {profile?.candidate?.headline && (
                <p className="text-small text-ink-600">{profile.candidate.headline}</p>
              )}
              {profile?.user?.phone && (
                <p className="text-micro text-ink-500">Phone: {profile.user.phone}</p>
              )}
            </>
          )}
        </CardBody>
        {onEditProfile && (
          <CardFooter>
            <Button variant="secondary" size="sm" onClick={onEditProfile}>
              Edit in Profile
            </Button>
          </CardFooter>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Market"
          description="Hireschema is India-only. Roles and salaries are scoped to India (INR)."
        />
        <CardBody className="space-y-3 !pt-0">
          <p className="rounded-md border border-ink-100 bg-paper-1 px-3 py-2.5 text-small text-ink-900">
            India · optional +91 phone (MSG91 OTP when verification is enabled)
          </p>
          <p className="text-micro text-ink-500">
            Fully remote roles may still show when eligible worldwide and allowed for India.
          </p>
        </CardBody>
      </Card>

      <CandidateSharingSettings />

      <TailoredResumeSettings />

      <Card>
        <CardHeader
          title="Notifications"
          description="Email alerts from Hireschema (via Resend). Turn a category off to stop those emails. Your one-time welcome email is sent at signup."
        />
        <CardBody className="space-y-0.5 !pt-0">
          {NOTIFICATION_CATEGORIES.map((cat) => (
            <div key={cat.id} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="text-small font-medium text-ink-900">{cat.label}</p>
                <p className="text-micro text-ink-500">{cat.desc}</p>
              </div>
              <Toggle
                checked={prefs[cat.id]?.email ?? true}
                onChange={(v) => setToggle(cat.id, v)}
              />
            </div>
          ))}
        </CardBody>
        <CardFooter>
          <Button variant="primary" size="sm" onClick={() => void savePrefs()} loading={savingPrefs}>
            Save preferences
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader
          title="Privacy"
          description="Your data, on your terms. DPDP Act 2023 compliant."
        />
        <CardBody className="space-y-2 !pt-0">
          <div className="flex flex-col gap-2 pt-1">
            <button
              onClick={() => void exportMyData()}
              className={BTN_ROW}
            >
              <Shield className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
              Export my data (JSON)
            </button>
            <Button variant="destructive" size="sm" onClick={() => void deleteAccount()} fullWidth>
              Delete my account
            </Button>
          </div>
        </CardBody>
      </Card>

      {onSignOut && (
        <Card>
          <CardHeader title="Account" />
          <CardBody className="!pt-0 space-y-3">
            <RoleSwitchButton
              to="recruiter"
              target="/recruiter/inbox"
              variant="banner"
            />
            <button
              onClick={onSignOut}
              disabled={signingOut}
              className={cn(BTN_ROW, "disabled:opacity-50")}
            >
              <LogOut className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

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
        checked ? "bg-accent" : "bg-ink-100",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-paper-1 shadow-1 transition-transform duration-fast",
          checked ? "translate-x-[18px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
