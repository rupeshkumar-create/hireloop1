"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRight, FileText, IndianRupee, Linkedin, MapPin, Mic, X } from "@/components/brand/icons";
import { ResumeUpload } from "@/components/resume/ResumeUpload";
import { Button, Card, CardBody } from "@/components/ui";
import { getCachedProfile, updateMyProfile } from "@/lib/api/profile";
import { isValidLinkedInUrl, saveLinkedInUrl } from "@/lib/api/onboardingProfile";
import {
  dismissProfileBoosters,
  isProfileBoostersDismissed,
} from "@/lib/profile/booster-dismiss";
import { marketByCode, type MarketCode } from "@/lib/markets";
import { profileSalaryToStorage, salaryInputLabel } from "@/lib/salary";
import { cn } from "@/lib/utils";

const FIELD_CLASS =
  "w-full rounded-md border border-ink-100 bg-paper-1 px-2.5 py-2 text-small text-ink-900 placeholder:text-ink-300 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring";

type ProfileBoostersProps = {
  hasResume: boolean;
  hasVoiceSession: boolean;
  canApply: boolean;
  onProfileUpdated?: () => void;
  className?: string;
};

export function ProfileBoosters({
  hasResume,
  hasVoiceSession,
  canApply,
  onProfileUpdated,
  className,
}: ProfileBoostersProps) {
  const [market, setMarket] = useState<MarketCode>("IN");
  const [locationCity, setLocationCity] = useState("");
  const [ctcMinLpa, setCtcMinLpa] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedPrefs, setSavedPrefs] = useState(false);
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [savingLi, setSavingLi] = useState(false);
  const [savedLi, setSavedLi] = useState(false);
  const [liError, setLiError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);

  const salaryLabel = salaryInputLabel(market);

  useEffect(() => {
    const profile = getCachedProfile();
    const id = profile?.user?.id ?? null;
    setUserId(id);
    if (id && isProfileBoostersDismissed(id)) {
      setDismissed(true);
    }
    const existingLi = profile?.candidate?.linkedin_url?.trim();
    if (existingLi) {
      setSavedLi(true);
      setLinkedinUrl(existingLi);
    }
    const m = profile?.user?.market;
    if (m) setMarket(marketByCode(m).code);
  }, []);

  async function saveLinkedin() {
    if (!isValidLinkedInUrl(linkedinUrl)) {
      setLiError("Enter a valid LinkedIn profile URL (linkedin.com/in/…).");
      return;
    }
    setSavingLi(true);
    setLiError(null);
    try {
      await saveLinkedInUrl(linkedinUrl);
      setSavedLi(true);
      onProfileUpdated?.();
    } catch (err) {
      setLiError(err instanceof Error ? err.message : "Couldn't save your LinkedIn URL.");
    } finally {
      setSavingLi(false);
    }
  }

  async function saveMinimalProfile() {
    const city = locationCity.trim();
    const sal = profileSalaryToStorage(ctcMinLpa, market);
    if (!city || sal == null) {
      setError(`Add your city and expected ${salaryLabel} to unlock apply and intros.`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateMyProfile({
        location_city: city,
        expected_ctc_min: sal,
      });
      setSavedPrefs(true);
      onProfileUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save preferences.");
    } finally {
      setSaving(false);
    }
  }

  function handleDismiss() {
    if (userId) dismissProfileBoosters(userId);
    setDismissed(true);
  }

  if (dismissed) return null;
  if (canApply && hasResume) return null;

  const showLinkedIn = !savedLi;
  const showResume = !hasResume;
  const showCityCtc = !canApply && !savedPrefs;
  const showVoice = !hasVoiceSession;

  if (!showLinkedIn && !showResume && !showCityCtc && !showVoice) return null;

  return (
    <Card className={cn("border-accent/20 bg-accent/5", className)}>
      <CardBody className="space-y-4 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-small font-semibold text-ink-900">
              {canApply ? "Boost your matches" : "Unlock apply & intros"}
            </p>
            <p className="mt-0.5 text-micro text-ink-500 leading-relaxed">
              {canApply
                ? "Add a CV or talk to Aarya to sharpen your match scores."
                : "Upload a resume or add city + expected CTC — then you can request intros and apply."}
            </p>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Dismiss profile suggestions"
            className="shrink-0 rounded-md p-1 text-ink-400 hover:text-ink-900 hover:bg-ink-50 transition-colors"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>

        {showLinkedIn && (
          <div className="rounded-lg border border-ink-100 bg-paper-0 p-3 space-y-2">
            <div className="flex items-center gap-2 text-small font-medium text-ink-900">
              <Linkedin className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
              Add your LinkedIn URL
            </div>
            <input
              type="url"
              inputMode="url"
              value={linkedinUrl}
              onChange={(e) => setLinkedinUrl(e.target.value)}
              placeholder="linkedin.com/in/your-profile"
              className={FIELD_CLASS}
            />
            {liError && <p className="text-micro text-destructive">{liError}</p>}
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              loading={savingLi}
              onClick={() => void saveLinkedin()}
            >
              Save &amp; enrich from LinkedIn
            </Button>
          </div>
        )}

        {showResume && (
          <div className="rounded-lg border border-ink-100 bg-paper-0 p-3 space-y-2">
            <div className="flex items-center gap-2 text-small font-medium text-ink-900">
              <FileText className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
              Upload resume
            </div>
            <ResumeUpload autoApply onDone={() => onProfileUpdated?.()} />
          </div>
        )}

        {showCityCtc && (
          <div className="rounded-lg border border-ink-100 bg-paper-0 p-3 space-y-3">
            <div className="flex items-center gap-2 text-small font-medium text-ink-900">
              <MapPin className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
              Or add city &amp; CTC
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="block space-y-1">
                <span className="text-micro text-ink-500">City</span>
                <input
                  value={locationCity}
                  onChange={(e) => setLocationCity(e.target.value)}
                  placeholder="Bangalore"
                  className={FIELD_CLASS}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-micro text-ink-500 flex items-center gap-1">
                  <IndianRupee className="h-3 w-3" />
                  {salaryLabel}
                </span>
                <input
                  type="number"
                  inputMode="decimal"
                  value={ctcMinLpa}
                  onChange={(e) => setCtcMinLpa(e.target.value)}
                  placeholder="18"
                  className={FIELD_CLASS}
                />
              </label>
            </div>
            {error && <p className="text-micro text-destructive">{error}</p>}
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              loading={saving}
              onClick={() => void saveMinimalProfile()}
            >
              Save & unlock apply
            </Button>
          </div>
        )}

        {showVoice && (
          <Link
            href="/dashboard?voice=deep&panel=jobs"
            className="group flex items-center justify-between rounded-lg border border-ink-100 bg-paper-0 px-3 py-2.5 hover:border-ink-200 transition-colors"
          >
            <span className="flex items-center gap-2 text-small font-medium text-ink-900">
              <Mic className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
              15-min call with Aarya
            </span>
            <ChevronRight
              className="h-4 w-4 text-ink-400 group-hover:translate-x-0.5 transition-transform"
              strokeWidth={1.5}
            />
          </Link>
        )}
      </CardBody>
    </Card>
  );
}
