"use client";

import { useEffect, useMemo, useState } from "react";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { ResumeUpload } from "@/components/resume/ResumeUpload";
import { SkillsInput } from "@/components/profile/SkillsInput";
import { BTN_PRIMARY, BTN_GHOST } from "@/lib/button-classes";
import { cn } from "@/lib/utils";

type ProfilePayload = {
  user: { full_name: string | null } | null;
  candidate: {
    headline: string | null;
    summary: string | null;
    current_title: string | null;
    current_company: string | null;
    years_experience: number | null;
    location_city: string | null;
    location_state: string | null;
    skills: string[];
    profile_complete: boolean;
  } | null;
};

export function ExperienceEnrichmentForm() {
  const [fullName, setFullName] = useState("");
  const [headline, setHeadline] = useState("");
  const [summary, setSummary] = useState("");
  const [currentTitle, setCurrentTitle] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [yearsExperience, setYearsExperience] = useState("");
  const [locationCity, setLocationCity] = useState("");
  const [locationState, setLocationState] = useState("");
  const [skills, setSkills] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      setError("");
      try {
        const res = await apiAuthFetch("/api/v1/me/profile", { cache: "no-store" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error((err as { detail?: string }).detail ?? "Failed to load profile");
        }
        const data = (await res.json()) as ProfilePayload;
        setFullName(data.user?.full_name ?? "");
        setHeadline(data.candidate?.headline ?? "");
        setSummary(data.candidate?.summary ?? "");
        setCurrentTitle(data.candidate?.current_title ?? "");
        setCurrentCompany(data.candidate?.current_company ?? "");
        setYearsExperience(
          data.candidate?.years_experience != null ? String(data.candidate.years_experience) : ""
        );
        setLocationCity(data.candidate?.location_city ?? "");
        setLocationState(data.candidate?.location_state ?? "");
        setSkills((data.candidate?.skills ?? []).join(", "));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load profile");
      } finally {
        setIsLoading(false);
      }
    };
    void load();
  }, []);

  const profileStrength = useMemo(() => {
    let score = 0;
    if (fullName.trim()) score += 1;
    if (currentTitle.trim()) score += 1;
    if (yearsExperience.trim()) score += 1;
    if (skills.trim()) score += 1;
    return Math.round((score / 4) * 100);
  }, [fullName, currentTitle, yearsExperience, skills]);

  async function saveProfile() {
    setIsSaving(true);
    setError("");
    setMessage("");
    try {
      const parsedYears = yearsExperience ? Number(yearsExperience) : null;
      const parsedSkills = skills
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await apiAuthFetch("/api/v1/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fullName || null,
          headline: headline || null,
          summary: summary || null,
          current_title: currentTitle || null,
          current_company: currentCompany || null,
          years_experience: Number.isFinite(parsedYears) ? parsedYears : null,
          location_city: locationCity || null,
          location_state: locationState || null,
          skills: parsedSkills,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? "Failed to save profile");
      }
      setMessage("Profile saved. You can continue to dashboard.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save profile");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-ink-100 bg-paper-1 p-6 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink-900">Profile enrichment</h2>
          <span className="rounded-full bg-ink-50 px-3 py-1 text-xs font-semibold text-accent">
            {profileStrength}% complete
          </span>
        </div>
        <p className="mb-5 text-sm text-ink-500">
          LinkedIn OIDC gives basic identity. Add resume/manual details so Aarya can rank better matches.
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Input label="Full name" value={fullName} onChange={setFullName} />
          <Input label="Headline" value={headline} onChange={setHeadline} placeholder="e.g. Backend Engineer" />
          <Input label="Current title" value={currentTitle} onChange={setCurrentTitle} />
          <Input label="Current company" value={currentCompany} onChange={setCurrentCompany} />
          <Input label="Years experience" value={yearsExperience} onChange={setYearsExperience} type="number" />
          <Input label="City" value={locationCity} onChange={setLocationCity} />
          <Input label="State" value={locationState} onChange={setLocationState} />
          <SkillsInput
            label="Skills (comma separated)"
            value={skills}
            onChange={setSkills}
            className="sm:col-span-2"
            placeholder="Python, FastAPI, React, PostgreSQL"
          />
          <Textarea
            label="Summary"
            value={summary}
            onChange={setSummary}
            className="sm:col-span-2"
            placeholder="Briefly describe your experience and focus areas."
          />
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={saveProfile}
            disabled={isSaving || isLoading}
            className={cn(BTN_PRIMARY, "px-4 py-2.5 text-sm font-semibold disabled:opacity-60")}
          >
            {isSaving ? "Saving..." : "Save profile"}
          </button>
          <button
            type="button"
            onClick={() => {
              window.location.href = "/dashboard";
            }}
            className={cn(BTN_GHOST, "px-4 py-2.5 text-sm font-semibold")}
          >
            Continue to dashboard
          </button>
        </div>

        {message && <p className="mt-3 text-sm text-ink-900">{message}</p>}
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        {isLoading && <p className="mt-3 text-sm text-ink-500">Loading profile...</p>}
      </section>

      <section className="rounded-2xl border border-ink-100 bg-paper-1 p-6 shadow-sm">
        <h2 className="mb-2 text-lg font-semibold text-ink-900">Resume import</h2>
        <p className="mb-4 text-sm text-ink-500">
          Upload resume to auto-extract experience, skills, and current role.
        </p>
        <ResumeUpload
          autoApply
          onDone={(resumeId) => {
            setMessage(`Resume ${resumeId.slice(0, 8)} imported into your profile.`);
          }}
        />
      </section>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  className = "",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-sm font-medium text-ink-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-ink-100 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent-ring"
      />
    </label>
  );
}

function Textarea({
  label,
  value,
  onChange,
  className = "",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  className?: string;
  placeholder?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-sm font-medium text-ink-700">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={4}
        className="w-full rounded-lg border border-ink-100 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent-ring"
      />
    </label>
  );
}

