"use client";

/**
 * Settings page — profile, notifications, privacy, account.
 *
 * Notification categories are defined CLIENT-SIDE so they always render with
 * proper human-readable labels. The API stores toggle state keyed by category id;
 * we never iterate over raw API keys to derive the category list.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { LogOut, Shield, User } from "lucide-react";
import { apiFetch } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/client";
import { fetchMyProfile, type MyProfileData, updateMyMarket } from "@/lib/api/profile";
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  useToast,
} from "@/components/ui";
import { AppShell } from "@/components/layout/AppShell";
import { NOTIFICATION_CATEGORIES } from "@/lib/notification-categories";
import { SUPPORTED_MARKETS, type MarketCode, marketByCode } from "@/lib/markets";
import { cn } from "@/lib/utils";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { toast } = useToast();

  const [signingOut, setSigningOut] = useState(false);
  const [market, setMarket] = useState<MarketCode>("IN");
  const [savingMarket, setSavingMarket] = useState(false);

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

  // Profile (read-only — career edits live in dashboard Profile panel)
  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [profileError, setProfileError] = useState("");

  // Notification prefs state — keyed by category id, value = { whatsapp: bool }
  const [prefs,       setPrefs]       = useState<Record<string, Record<string, boolean>>>({});
  const [savingPrefs, setSavingPrefs] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoadingProfile(true);
      setProfileError("");
      try {
        const d = await fetchMyProfile();
        setProfile(d);
        const nextMarket = (d.user?.market ?? "IN") as MarketCode;
        setMarket(marketByCode(nextMarket).code);
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

  async function saveMarket() {
    if (savingMarket) return;
    setSavingMarket(true);
    try {
      await updateMyMarket(market);
      const refreshed = await fetchMyProfile({ force: true });
      setProfile(refreshed);
      toast.success("Market updated");
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : "Couldn't update market";
      toast.error(msg);
    } finally {
      setSavingMarket(false);
    }
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

  const displayName =
    profile?.user?.full_name?.trim() ||
    profile?.candidate?.headline?.trim() ||
    "Your profile";

  return (
    <AppShell title="Settings">
      <div className="space-y-4">
        <Card>
          <CardHeader
            title="Career profile"
            description="Headline, experience, resume, and career story"
          />
          <CardBody className="space-y-3 !pt-0">
            {profileError && (
              <p className="text-small text-destructive">{profileError}</p>
            )}
            {loadingProfile ? (
              <p className="text-small text-ink-500">Loading…</p>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-ink-100 flex items-center justify-center shrink-0">
                    <User className="h-5 w-5 text-ink-500" strokeWidth={1.5} />
                  </div>
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
          <CardFooter>
            <Link
              href="/dashboard?panel=profile"
              className="inline-flex items-center justify-center font-medium h-9 px-3 text-small rounded-md border border-ink-200 bg-transparent text-ink-900 hover:bg-ink-50 hover:border-ink-300 transition-colors"
            >
              Edit in Profile
            </Link>
          </CardFooter>
        </Card>

        {/* Market */}
        <Card>
          <CardHeader
            title="Market"
            description="Your home job market. Roles and salaries are scoped to this region."
          />
          <CardBody className="space-y-3 !pt-0">
            <label htmlFor="settings-market" className="text-small font-medium text-ink-700">
              Home market
            </label>
            <select
              id="settings-market"
              value={market}
              onChange={(e) => setMarket(e.target.value as MarketCode)}
              className="h-10 w-full rounded-md border border-ink-200 bg-paper-0 px-3 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent/25"
            >
              {SUPPORTED_MARKETS.map((m) => (
                <option key={m.code} value={m.code}>
                  {m.label}
                </option>
              ))}
            </select>
            <p className="text-micro text-ink-500">
              You can switch markets anytime. If you have a verified phone, it must
              match the new region (+91 / +1 / +44). Fully remote roles may still
              show if eligible worldwide.
            </p>
          </CardBody>
          <CardFooter>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void saveMarket()}
              loading={savingMarket}
            >
              Save market
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
