"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  Briefcase,
  Building2,
  Copy,
  ExternalLink,
  FileText,
  GraduationCap,
  Linkedin,
  LinkIcon,
  Loader2,
  MapPin,
  Shield,
} from "@/components/brand/icons";
import { apiFetch } from "@/lib/api/client";
import {
  applyProfileToForm,
  fetchMyProfile,
  getCachedProfile,
  invalidateProfileCache,
  publishPublicProfile,
  REMOTE_PREFERENCE_OPTIONS,
  updateRemotePreference,
  type Education,
  type MyProfileData,
  type RemotePreference,
  type WorkExperience,
} from "@/lib/api/profile";
import { isValidLinkedInUrl, linkedInProfileId, saveLinkedInUrl } from "@/lib/api/onboardingProfile";
import { CareerIntelligencePanel } from "@/components/profile/CareerIntelligencePanel";
import { GoogleConnectCard } from "@/components/profile/GoogleConnectCard";
import { ResumeUpload } from "@/components/resume/ResumeUpload";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";
import { BTN_CHIP, BTN_CHIP_ACTIVE, BTN_GHOST, BTN_ROW } from "@/lib/button-classes";
import type { PanelId, ProfileTabId } from "@/lib/dashboard/panel-types";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  EmptyState,
  useToast,
} from "@/components/ui";

type ProfileTab = ProfileTabId;

function ProfileSkeleton() {
  return (
    <div className="animate-skeleton space-y-4" aria-hidden="true">
      <Card>
        <CardBody className="space-y-4">
          <div className="h-4 w-32 rounded bg-ink-100" />
          <div className="h-9 w-full rounded bg-ink-100" />
          <div className="h-20 w-full rounded bg-ink-100" />
          <div className="grid grid-cols-2 gap-3">
            <div className="h-9 rounded bg-ink-100" />
            <div className="h-9 rounded bg-ink-100" />
          </div>
          <div className="flex flex-wrap gap-1.5 pt-1">
            <div className="h-5 w-16 rounded-full bg-ink-100" />
            <div className="h-5 w-20 rounded-full bg-ink-100" />
            <div className="h-5 w-14 rounded-full bg-ink-100" />
            <div className="h-5 w-24 rounded-full bg-ink-100" />
          </div>
        </CardBody>
      </Card>
      <Card>
        <CardBody className="space-y-3">
          <div className="h-4 w-40 rounded bg-ink-100" />
          <div className="h-16 w-full rounded bg-ink-100" />
        </CardBody>
      </Card>
    </div>
  );
}

export function ProfilePanel({
  onSendToChat,
  onOpenPanel,
  initialTab,
}: {
  /** Forwarded to Career Intelligence so its insights can trigger Aarya actions. */
  onSendToChat?: (message: string) => void;
  onOpenPanel?: (id: PanelId) => void;
  initialTab?: ProfileTab;
} = {}) {
  const { toast } = useToast();

  const [tab, setTab] = useState<ProfileTab>(initialTab ?? "overview");

  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [experience, setExperience] = useState<WorkExperience[]>([]);
  const [education, setEducation] = useState<Education[]>([]);

  const [fullName, setFullName] = useState("");
  const [headline, setHeadline] = useState("");
  const [currentTitle, setCurrentTitle] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [summary, setSummary] = useState("");
  const [lookingFor, setLookingFor] = useState("");

  const [loadingProfile, setLoadingProfile] = useState(() => getCachedProfile() === null);
  const [profileError, setProfileError] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [remotePref, setRemotePref] = useState<RemotePreference>("any");
  const [savingRemote, setSavingRemote] = useState<RemotePreference | null>(null);
  const [linkedinDraft, setLinkedinDraft] = useState("");
  const [savingLinkedin, setSavingLinkedin] = useState(false);
  const [linkedinError, setLinkedinError] = useState("");
  const [publishingPublic, setPublishingPublic] = useState(false);

  function hydrate(d: MyProfileData) {
    applyProfileToForm(d, {
      setProfile,
      setFullName,
      setHeadline,
      setCurrentTitle,
      setSummary,
      setCurrentCompany,
      setLookingFor,
    });
    const pref = d.candidate?.remote_preference;
    if (pref === "any" || pref === "remote_only" || pref === "onsite_only") {
      setRemotePref(pref);
    } else {
      setRemotePref("any");
    }
    setExperience(d.experience ?? []);
    setEducation(d.education ?? []);
  }

  async function selectRemotePreference(next: RemotePreference) {
    if (next === remotePref || savingRemote) return;
    const prev = remotePref;
    setRemotePref(next);
    setSavingRemote(next);
    try {
      await updateRemotePreference(next);
      invalidateProfileCache();
      toast.success("Job search filter updated");
    } catch {
      setRemotePref(prev);
      toast.error("Couldn't update job filter");
    } finally {
      setSavingRemote(null);
    }
  }

  useEffect(() => {
    const loadProfile = async () => {
      const cached = getCachedProfile();
      if (cached) {
        hydrate(cached);
        setLoadingProfile(false);
      } else {
        setLoadingProfile(true);
      }
      setProfileError("");
      try {
        hydrate(await fetchMyProfile());
      } catch (err) {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (user) {
          const meta = user.user_metadata as Record<string, unknown> | undefined;
          const name =
            (typeof meta?.full_name === "string" && meta.full_name) ||
            (typeof meta?.name === "string" && meta.name) ||
            "";
          setFullName(name);
          setProfile({
            user: { id: user.id, email: user.email ?? "", phone: null, full_name: name || null },
            candidate: null,
          });
        }
        setProfileError(
          err instanceof Error
            ? err.message
            : "Couldn't load profile. Check that the API is running.",
        );
      } finally {
        setLoadingProfile(false);
      }
    };

    void loadProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (tab !== "experience" && tab !== "intelligence") return;
    void fetchMyProfile({ force: true })
      .then(hydrate)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function handleSaveProfile() {
    setSavingProfile(true);
    try {
      await apiFetch("/api/v1/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: fullName.trim() || undefined,
          headline: headline.trim() || undefined,
          current_title: currentTitle.trim() || undefined,
          current_company: currentCompany.trim() || undefined,
          summary: summary.trim() || undefined,
          looking_for: lookingFor.trim() || undefined,
        }),
      });
      hydrate(await fetchMyProfile({ force: true }));
      setProfileError("");
      toast.success("Profile updated");
    } catch {
      toast.error("Couldn't update profile");
    } finally {
      setSavingProfile(false);
    }
  }

  const inputClass =
    "w-full px-3 py-2 rounded-md border border-ink-200 bg-paper-0 text-small text-ink-900 " +
    "placeholder:text-ink-400 focus:outline-none focus:ring-1 focus:ring-ink-900 transition-shadow";

  const name = fullName || profile?.user?.full_name || "Your profile";
  const initials =
    name
      .split(" ")
      .map((p) => p[0])
      .slice(0, 2)
      .join("")
      .toUpperCase() || "U";
  const isActive = profile?.candidate?.is_active !== false;
  const linkedinUrl = profile?.candidate?.linkedin_url?.trim() || null;
  const linkedinId = linkedInProfileId(linkedinUrl);
  const publicEnabled = Boolean(profile?.candidate?.public_profile_enabled);
  const publicPath = profile?.candidate?.public_profile_url ?? null;
  const publicUrl =
    typeof window !== "undefined" && publicPath
      ? `${window.location.origin}${publicPath}`
      : publicPath;

  async function handleSaveLinkedin() {
    if (!isValidLinkedInUrl(linkedinDraft)) {
      setLinkedinError("Enter a valid LinkedIn URL (linkedin.com/in/your-name).");
      return;
    }
    setSavingLinkedin(true);
    setLinkedinError("");
    try {
      await saveLinkedInUrl(linkedinDraft);
      hydrate(await fetchMyProfile({ force: true }));
      setLinkedinDraft("");
      toast.success("LinkedIn profile saved");
    } catch (err) {
      setLinkedinError(err instanceof Error ? err.message : "Couldn't save LinkedIn URL");
    } finally {
      setSavingLinkedin(false);
    }
  }

  async function handlePublishPublic() {
    if (publishingPublic) return;
    setPublishingPublic(true);
    try {
      const res = await publishPublicProfile();
      hydrate(await fetchMyProfile({ force: true }));
      toast.success("Your public profile is live");
      if (res.public_profile_url) {
        const full =
          typeof window !== "undefined"
            ? `${window.location.origin}${res.public_profile_url}`
            : res.public_profile_url;
        try {
          await navigator.clipboard.writeText(full);
        } catch {
          /* clipboard optional */
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't publish public profile");
    } finally {
      setPublishingPublic(false);
    }
  }

  async function handleCopyPublicLink() {
    if (!publicUrl) return;
    try {
      await navigator.clipboard.writeText(publicUrl);
      toast.success("Public link copied");
    } catch {
      toast.error("Couldn't copy — please copy the link manually");
    }
  }

  const TABS: { id: ProfileTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "experience", label: "Experience" },
    { id: "intelligence", label: "Intelligence" },
    { id: "preferences", label: "Preferences" },
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 pt-5 pb-3">
        <div className="flex items-start gap-3">
          {profile?.user?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.user.avatar_url}
              alt={name}
              className="w-14 h-14 rounded-full object-cover shrink-0"
            />
          ) : (
            <div className="w-14 h-14 rounded-full bg-ink-900 flex items-center justify-center shrink-0">
              <span className="text-paper-0 text-h3 font-semibold">{initials}</span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-h3 font-semibold text-ink-900 truncate">{name}</h3>
              {isActive && (
                <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-micro font-medium text-accent">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                  Actively Looking
                </span>
              )}
            </div>
            <p className="text-small text-ink-500 truncate mt-0.5">
              {headline || "Add a headline to stand out"}
            </p>

            <div className="mt-2 space-y-1.5">
              <div className="flex items-start gap-2 min-w-0">
                <Linkedin className="h-3.5 w-3.5 text-ink-400 shrink-0 mt-0.5" strokeWidth={1.5} />
                {linkedinId ? (
                  <div className="min-w-0">
                    <p className="text-micro text-ink-500">LinkedIn</p>
                    <a
                      href={linkedinUrl!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-small font-medium text-ink-900 hover:text-accent truncate block"
                    >
                      linkedin.com/in/{linkedinId}
                    </a>
                  </div>
                ) : (
                  <div className="flex-1 min-w-0 space-y-1">
                    <p className="text-micro text-ink-500">LinkedIn not saved yet</p>
                    <div className="flex items-center gap-1.5">
                      <input
                        type="url"
                        value={linkedinDraft}
                        onChange={(e) => {
                          setLinkedinDraft(e.target.value);
                          setLinkedinError("");
                        }}
                        placeholder="linkedin.com/in/your-profile"
                        className="flex-1 min-w-0 h-8 rounded-md border border-ink-200 bg-paper-0 px-2 text-micro text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-1 focus:ring-ink-900"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={savingLinkedin}
                        onClick={() => void handleSaveLinkedin()}
                        className="shrink-0 h-8 px-2.5 text-micro"
                      >
                        Save
                      </Button>
                    </div>
                    {linkedinError && (
                      <p className="text-micro text-destructive">{linkedinError}</p>
                    )}
                  </div>
                )}
              </div>

              <div className="flex items-start gap-2 min-w-0">
                <LinkIcon className="h-3.5 w-3.5 text-ink-400 shrink-0 mt-0.5" strokeWidth={1.5} />
                {publicEnabled && publicUrl ? (
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-micro text-ink-500">Live public link</p>
                      <span className="inline-flex items-center rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                        Live
                      </span>
                    </div>
                    <p className="text-small font-medium text-ink-900 break-all">{publicUrl}</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <button
                        type="button"
                        onClick={() => void handleCopyPublicLink()}
                        className={cn(
                          BTN_GHOST,
                          "inline-flex items-center gap-1 px-2 py-1 text-micro",
                        )}
                      >
                        <Copy className="h-3 w-3" strokeWidth={1.5} />
                        Copy
                      </button>
                      <Link
                        href={publicPath ?? "/dashboard"}
                        target="_blank"
                        className={cn(
                          BTN_GHOST,
                          "inline-flex items-center gap-1 px-2 py-1 text-micro",
                        )}
                      >
                        <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                        Open
                      </Link>
                    </div>
                  </div>
                ) : (
                  <div className="flex-1 min-w-0">
                    <p className="text-micro text-ink-500">Live public link</p>
                    <p className="text-small text-ink-600">
                      Share a recruiter-friendly profile page.
                    </p>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={publishingPublic}
                      onClick={() => void handlePublishPublic()}
                      className="mt-1 h-8 px-2.5 text-micro"
                    >
                      Go live
                    </Button>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 mt-2">
              {linkedinUrl && !linkedinId && (
                <a
                  href={linkedinUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(BTN_GHOST, "inline-flex items-center gap-1.5 px-2.5 py-1.5 text-micro")}
                >
                  <Linkedin className="h-3.5 w-3.5" strokeWidth={1.5} />
                  View LinkedIn
                </a>
              )}
              <button
                type="button"
                onClick={() => setTab("overview")}
                className={cn(BTN_GHOST, "inline-flex items-center gap-1.5 px-2.5 py-1.5 text-micro")}
              >
                <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
                Update CV
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1 px-5 border-b border-ink-100">
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "px-3 py-2 text-small font-medium border-b-2 -mb-px transition-colors duration-fast",
                active
                  ? "border-ink-900 text-ink-900"
                  : "border-transparent text-ink-400 hover:text-ink-700",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div key={tab} className="flex-1 overflow-y-auto p-5 space-y-4 animate-fade-in">
        {loadingProfile && <ProfileSkeleton />}
        {profileError && <p className="text-small text-ink-700">{profileError}</p>}

        {tab === "overview" && !loadingProfile && (
          <>
            <p className="text-small text-ink-500">
              Account, notifications, and privacy live in{" "}
              {onOpenPanel ? (
                <button
                  type="button"
                  onClick={() => onOpenPanel("settings")}
                  className="text-accent font-medium hover:underline"
                >
                  Settings
                </button>
              ) : (
                <Link href="/dashboard?panel=settings" className="text-accent font-medium hover:underline">
                  Settings
                </Link>
              )}
              .
            </p>
            <GoogleConnectCard />
            <Card>
              <CardHeader title="Overview" description={profile?.user?.email ?? undefined} />
              <CardBody className="space-y-3 !pt-0">
                <Field label="Headline">
                  <input
                    className={inputClass}
                    value={headline}
                    onChange={(e) => setHeadline(e.target.value)}
                    placeholder="e.g. Senior Software Engineer"
                  />
                </Field>
                <Field label="Summary">
                  <textarea
                    className={cn(inputClass, "min-h-[88px] resize-y")}
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                    placeholder="A short bio or career summary"
                  />
                </Field>
                <Field label="What I'm looking for">
                  <textarea
                    className={cn(inputClass, "min-h-[72px] resize-y")}
                    value={lookingFor}
                    onChange={(e) => setLookingFor(e.target.value)}
                    placeholder="The kind of role / opportunity you want next"
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Current role">
                    <input
                      className={inputClass}
                      value={currentTitle}
                      onChange={(e) => setCurrentTitle(e.target.value)}
                      placeholder="e.g. Sales Lead"
                    />
                  </Field>
                  <Field label="Company">
                    <input
                      className={inputClass}
                      value={currentCompany}
                      onChange={(e) => setCurrentCompany(e.target.value)}
                      placeholder="e.g. Hireschema"
                    />
                  </Field>
                </div>

                {profile?.candidate?.skills && profile.candidate.skills.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">
                      Skills
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.candidate.skills.slice(0, 14).map((s) => (
                        <span
                          key={s}
                          className="px-2 py-0.5 rounded-full bg-ink-100 text-micro text-ink-700 font-medium"
                        >
                          {s}
                        </span>
                      ))}
                      {profile.candidate.skills.length > 14 && (
                        <span className="px-2 py-0.5 rounded-full bg-ink-100 text-micro text-ink-500">
                          +{profile.candidate.skills.length - 14} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </CardBody>
              <CardFooter>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleSaveProfile()}
                  loading={savingProfile}
                >
                  Save profile
                </Button>
              </CardFooter>
            </Card>

            <Card>
              <CardHeader
                title="Resume / CV"
                description="Upload a new CV and Aarya will re-extract your details and update your profile."
              />
              <CardBody className="!pt-0">
                <ResumeUpload
                  autoApply
                  currentFileName={profile?.resume_filename ?? null}
                  onDone={async (_id, parsed) => {
                    const wasFirstResume = !profile?.resume_filename;
                    try {
                      hydrate(await fetchMyProfile());
                      setProfileError("");
                    } catch {
                      /* keep parsed preview even if re-fetch fails */
                    }
                    const count = parsed.skills?.length ?? 0;
                    toast.success(
                      count
                        ? `Profile updated from your CV — ${count} skills detected`
                        : "Profile updated from your CV",
                    );
                    // If this was their first resume, immediately run the 3-step kickoff
                    // (analysis → pick path → review → job search) on the dashboard.
                    if (wasFirstResume) {
                      window.location.replace("/dashboard?kickoff=career");
                    }
                  }}
                />
              </CardBody>
            </Card>
          </>
        )}

        {tab === "experience" && !loadingProfile && (
          <>
            <Card>
              <CardHeader
                title="Experience"
                description="Merged from LinkedIn, your CV, and Aarya's analysis of each role."
              />
              <CardBody className="!pt-0">
                {experience.length === 0 ? (
                  <EmptyState
                    icon={<Briefcase strokeWidth={1.5} />}
                    title="No experience yet"
                    description="Connect LinkedIn or upload your CV in Overview — Aarya will fill this in with her take on each role."
                  />
                ) : (
                  <ol className="relative space-y-0">
                    {experience.map((exp, i) => (
                      <ExperienceItem
                        key={`${exp.company}-${i}`}
                        exp={exp}
                        last={i === experience.length - 1}
                      />
                    ))}
                  </ol>
                )}
              </CardBody>
            </Card>

            {education.length > 0 && (
              <Card>
                <CardHeader title="Education" />
                <CardBody className="!pt-0 space-y-3">
                  {education.map((ed, i) => (
                    <div key={`${ed.institution}-${i}`} className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-md bg-ink-100 flex items-center justify-center shrink-0 mt-0.5">
                        <GraduationCap className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-small font-medium text-ink-900">
                          {ed.institution ?? "—"}
                        </p>
                        <p className="text-micro text-ink-500">
                          {[ed.degree, ed.field_of_study].filter(Boolean).join(" · ") || "—"}
                        </p>
                        {(ed.start_date || ed.end_date) && (
                          <p className="text-micro text-ink-400">
                            {[ed.start_date, ed.end_date].filter(Boolean).join(" – ")}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}
          </>
        )}

        {tab === "intelligence" && <CareerIntelligencePanel onAskAarya={onSendToChat} />}

        {tab === "preferences" && (
          <>
            <Card>
              <CardHeader
                title="Account & notifications"
                description="Privacy, WhatsApp alerts, and sign out"
              />
              <CardBody className="!pt-0">
                {onOpenPanel ? (
                  <button
                    type="button"
                    onClick={() => onOpenPanel("settings")}
                    className={cn(BTN_ROW, "justify-between")}
                  >
                    <span>Open Settings</span>
                    <span className="text-ink-400">→</span>
                  </button>
                ) : (
                  <Link
                    href="/dashboard?panel=settings"
                    className={cn(BTN_ROW, "justify-between")}
                  >
                    <span>Open Settings</span>
                    <span className="text-ink-400">→</span>
                  </Link>
                )}
              </CardBody>
            </Card>

            {profile?.user?.phone && (
              <Card>
                <CardBody className="!py-3">
                  <p className="text-small text-ink-600">
                    Phone: <span className="text-ink-900">{profile.user.phone}</span>
                  </p>
                </CardBody>
              </Card>
            )}

            <Card>
              <CardHeader
                title="Job search"
                description="Filter matches in Jobs and when Aarya searches for you. You can also change this in chat."
              />
              <CardBody className="!pt-0 space-y-2">
                {REMOTE_PREFERENCE_OPTIONS.map((opt) => {
                  const isActive = remotePref === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => void selectRemotePreference(opt.id)}
                      disabled={savingRemote !== null}
                      className={cn(
                        "w-full flex items-start gap-3 px-3 py-2.5 text-left",
                        isActive ? BTN_CHIP_ACTIVE : BTN_CHIP,
                        savingRemote !== null && "opacity-70",
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <p
                          className={cn(
                            "text-small font-medium",
                            isActive ? "text-ink-900" : "text-ink-700",
                          )}
                        >
                          {opt.label}
                        </p>
                        <p className="text-micro text-ink-500 mt-0.5">{opt.hint}</p>
                      </div>
                      {savingRemote === opt.id ? (
                        <Loader2
                          className="h-4 w-4 text-ink-400 animate-spin shrink-0 mt-0.5"
                          strokeWidth={1.5}
                        />
                      ) : (
                        isActive && (
                          <span className="w-2 h-2 rounded-full bg-accent shrink-0 mt-1.5" />
                        )
                      )}
                    </button>
                  );
                })}
              </CardBody>
            </Card>

            {profile?.user?.is_admin && (
              <Card>
                <CardHeader
                  title="Admin"
                  description="Internal — user management, bias audit & observability."
                />
                <CardBody className="!pt-0">
                  <a
                    href="/admin"
                    className={cn(BTN_ROW)}
                  >
                    <Shield className="h-4 w-4 text-ink-400 shrink-0" strokeWidth={1.5} />
                    Open admin panel
                  </a>
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-micro text-ink-500 font-medium uppercase tracking-wide">{label}</span>
      {children}
    </label>
  );
}

function ExperienceItem({ exp, last }: { exp: WorkExperience; last: boolean }) {
  const dates = [exp.start_date, exp.is_current ? "Present" : exp.end_date]
    .filter(Boolean)
    .join(" – ");
  const meta = [exp.location, exp.industry, exp.employment_type, exp.seniority]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="relative flex gap-3 pb-4">
      <div className="flex flex-col items-center">
        <div className="w-9 h-9 rounded-md bg-ink-100 flex items-center justify-center shrink-0">
          <Building2 className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
        </div>
        {!last && <span className="w-px flex-1 bg-ink-100 mt-1" />}
      </div>
      <div className="min-w-0 pb-1 space-y-1.5">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-small font-semibold text-ink-900">{exp.title ?? "—"}</p>
            {exp.company && <p className="text-micro text-ink-600">{exp.company}</p>}
          </div>
          {exp.source === "linkedin" && <Badge className="shrink-0">LinkedIn</Badge>}
        </div>
        {meta && <p className="text-micro text-ink-500">{meta}</p>}
        {dates && (
          <p className="text-micro text-ink-400 flex items-center gap-1">
            <MapPin className="h-3 w-3" strokeWidth={1.5} />
            {dates}
          </p>
        )}
        {exp.description && (
          <p className="text-micro text-ink-500 leading-snug">{exp.description}</p>
        )}
        {exp.aarya_insights && exp.aarya_insights.length > 0 && (
          <div className="rounded-md bg-ink-50 border border-ink-100 px-3 py-2 mt-1">
            <p className="text-micro font-medium text-ink-700 mb-1">Aarya&apos;s take</p>
            <ul className="list-disc pl-4 space-y-0.5">
              {exp.aarya_insights.map((line, idx) => (
                <li key={idx} className="text-micro text-ink-600 leading-snug">
                  {line}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </li>
  );
}
