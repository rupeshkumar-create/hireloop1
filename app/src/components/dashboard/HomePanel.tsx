"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Briefcase,
  Check,
  Circle,
  Eye,
  EyeOff,
  FileText,
  IndianRupee,
  Loader2,
  Phone,
  Search,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import {
  fetchMyProfile,
  getCachedProfile,
  invalidateProfileCache,
  updateProfileVisibility,
  type CandidateVisibility,
  type MyProfileData,
} from "@/lib/api/profile";
import {
  DEFAULT_MATCH_FEED_FILTERS,
  fetchMatchFeedCount,
  getCachedMatchFeedCount,
} from "@/lib/api/matches";
import { fetchIntros, getCachedIntros, type IntroRequest } from "@/lib/api/intros";
import { fetchCareerIntelligence, fetchCareerPath } from "@/lib/api/career";
import { fetchGoogleStatus } from "@/lib/api/gmail";
import { CareerPathOptionCards } from "@/components/career/CareerPathOptionCards";
import { CollapsibleSection } from "@/components/dashboard/CollapsibleSection";
import { HomeMissionHero } from "@/components/dashboard/HomeMissionHero";
import { ProfileBoosters } from "@/components/onboarding/ProfileBoosters";
import type { PanelId } from "@/lib/dashboard/panel-types";
import { IntelligenceHero } from "@/components/ux";
import { FadeUp } from "@/components/ui/motion";
import { cn } from "@/lib/utils";
import { Button, Card, CardBody, useToast } from "@/components/ui";

const VISIBILITY_OPTIONS: {
  id: CandidateVisibility;
  label: string;
  hint: string;
  Icon: React.ElementType;
}[] = [
  {
    id: "open_to_matches",
    label: "Open to matches",
    hint: "You'll be shared with companies where Aarya sees a strong fit.",
    Icon: Eye,
  },
  {
    id: "exceptional_only",
    label: "Exceptional only",
    hint: "You'll only be shared for roles that are an exceptional fit.",
    Icon: Sparkles,
  },
  {
    id: "private",
    label: "Don't share",
    hint: "Your profile is never shared automatically. You stay invisible to companies.",
    Icon: EyeOff,
  },
];

export type HomePanelProps = {
  candidateName?: string;
  showProfileBoosters?: boolean;
  hasResume?: boolean;
  hasVoiceSession?: boolean;
  canApply?: boolean;
  onProfileBoosted?: () => void;
  onSendToChat: (text: string) => void;
  onOpenPanel: (id: PanelId) => void;
};

function SetupChecklist({
  profile,
  googleConnected,
  jobCount,
  onOpenPanel,
}: {
  profile: MyProfileData | null;
  googleConnected: boolean | null;
  jobCount: number | null;
  onOpenPanel: (id: PanelId) => void;
}) {
  const profileDone = profile?.candidate?.profile_complete === true;
  const resumeDone = !!profile?.resume_filename;
  const googleDone = googleConnected === true;
  const [careerPathDone, setCareerPathDone] = useState(false);

  useEffect(() => {
    if (!profileDone || !resumeDone) return;
    let cancelled = false;
    fetchCareerPath()
      .then((p) => {
        if (!cancelled) {
          setCareerPathDone(Boolean(p?.steps?.length || p?.target_titles?.length));
        }
      })
      .catch(() => {
        if (!cancelled) setCareerPathDone(false);
      });
    return () => {
      cancelled = true;
    };
  }, [profileDone, resumeDone]);

  const steps = [
    {
      id: "profile",
      label: "Complete your profile",
      hint: "Add your title, experience, skills & expectations.",
      done: profileDone,
      cta: "Complete",
    },
    {
      id: "resume",
      label: "Add your résumé",
      hint: "Aarya auto-fills your profile straight from it.",
      done: resumeDone,
      cta: "Upload",
    },
    {
      id: "paths",
      label: "Review career paths",
      hint: "Pick a direction before Aarya searches roles.",
      done: careerPathDone,
      cta: "View paths",
      panel: "jobs" as PanelId,
    },
    {
      id: "google",
      label: "Connect Google (optional)",
      hint: "Send intros from your Gmail and get Meet links on calls.",
      done: googleDone,
      cta: "Connect",
    },
  ];

  if (profile === null) return null;
  if (steps.every((s) => s.done)) return null;

  const doneCount = steps.filter((s) => s.done).length;
  const essentialsDone = profileDone && resumeDone && careerPathDone;

  return (
    <FadeUp>
      <Card>
        <CardBody className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.5} />
              <p className="text-small font-semibold text-ink-900">Finish setting up</p>
            </div>
            <span className="text-micro text-ink-500">
              {doneCount}/{steps.length} done
            </span>
          </div>

          <ul className="space-y-1.5">
            {steps.map((s) => (
              <li key={s.id} className="flex items-center gap-3">
                {s.done ? (
                  <Check className="h-4 w-4 text-ink-900 shrink-0" strokeWidth={2} />
                ) : (
                  <Circle className="h-4 w-4 text-ink-300 shrink-0" strokeWidth={1.5} />
                )}
                <div className="min-w-0 flex-1">
                  <p
                    className={cn(
                      "text-small",
                      s.done ? "text-ink-400 line-through" : "text-ink-800 font-medium",
                    )}
                  >
                    {s.label}
                  </p>
                  {!s.done && <p className="text-micro text-ink-500">{s.hint}</p>}
                </div>
                {!s.done && (
                  <button
                    type="button"
                    onClick={() =>
                      onOpenPanel("panel" in s && s.panel ? s.panel : "profile")
                    }
                    className="shrink-0 inline-flex items-center rounded-full border border-ink-200 bg-paper-0 px-3 py-1 text-micro font-medium text-ink-700 hover:border-ink-300 hover:bg-ink-50 transition-colors"
                  >
                    {s.cta}
                  </button>
                )}
              </li>
            ))}
          </ul>

          {essentialsDone && jobCount != null && jobCount > 0 && (
            <button
              type="button"
              onClick={() => onOpenPanel("jobs")}
              className="w-full inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-2 text-small font-medium text-on-accent hover:bg-accent-hover transition-colors"
            >
              <Search className="h-4 w-4" strokeWidth={1.5} />
              See your {jobCount} {jobCount === 1 ? "match" : "matches"}
            </button>
          )}
        </CardBody>
      </Card>
    </FadeUp>
  );
}

export function HomePanel({
  candidateName,
  showProfileBoosters,
  hasResume,
  hasVoiceSession,
  canApply,
  onProfileBoosted,
  onSendToChat,
  onOpenPanel,
}: HomePanelProps) {
  const { toast } = useToast();
  const firstName = candidateName?.split(" ")[0] ?? "there";

  const activeIntroCount = (rows: IntroRequest[]) =>
    rows.filter((r) => !["declined", "expired", "cancelled"].includes(r.status)).length;

  const [jobCount, setJobCount] = useState<number | null>(
    () => getCachedMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS),
  );
  const [introCount, setIntroCount] = useState<number | null>(() => {
    const cached = getCachedIntros();
    return cached ? activeIntroCount(cached) : null;
  });
  const [visibility, setVisibility] = useState<CandidateVisibility | null>(
    () => getCachedProfile()?.candidate?.visibility ?? null,
  );
  const [savingVis, setSavingVis] = useState<CandidateVisibility | null>(null);
  const [profileData, setProfileData] = useState<MyProfileData | null>(() => getCachedProfile());
  const [googleConnected, setGoogleConnected] = useState<boolean | null>(null);
  const [hasCareerPath, setHasCareerPath] = useState(false);
  const [intelArchetype, setIntelArchetype] = useState<string | null>(null);
  const [intelNextRole, setIntelNextRole] = useState<string | null>(null);
  const [intelCompleteness, setIntelCompleteness] = useState<number | null>(null);

  useEffect(() => {
    fetchMatchFeedCount(DEFAULT_MATCH_FEED_FILTERS)
      .then((total) => setJobCount(total))
      .catch(() => setJobCount(0));

    fetchIntros()
      .then((rows) => setIntroCount(activeIntroCount(rows)))
      .catch(() => setIntroCount(0));

    fetchMyProfile()
      .then((d) => {
        setProfileData(d);
        setVisibility(d.candidate?.visibility ?? "open_to_matches");
      })
      .catch(() => setVisibility("open_to_matches"));

    fetchGoogleStatus()
      .then((s) => setGoogleConnected(s.connected))
      .catch(() => setGoogleConnected(null));

    fetchCareerPath()
      .then((p) => setHasCareerPath(Boolean(p?.steps?.length || p?.target_titles?.length)))
      .catch(() => setHasCareerPath(false));

    fetchCareerIntelligence()
      .then((intel) => {
        if (!intel) return;
        setIntelArchetype(intel.career_dna?.primary_archetype ?? null);
        setIntelNextRole(intel.prediction?.most_likely_next_role?.outcome ?? null);
        setIntelCompleteness(intel.data_completeness ?? null);
      })
      .catch(() => {});
  }, []);

  async function selectVisibility(next: CandidateVisibility) {
    if (next === visibility || savingVis) return;
    const prev = visibility;
    setVisibility(next);
    setSavingVis(next);
    try {
      await updateProfileVisibility(next);
      invalidateProfileCache();
      toast.success("Visibility updated");
    } catch {
      setVisibility(prev);
      toast.error("Couldn't update visibility");
    } finally {
      setSavingVis(null);
    }
  }

  const QUICK_ACTIONS: {
    label: string;
    Icon: React.ElementType;
    onClick: () => void;
  }[] = [
    { label: "See my matches", Icon: Briefcase, onClick: () => onOpenPanel("jobs") },
    {
      label: "Plan career paths",
      Icon: Search,
      onClick: () =>
        onSendToChat("Show me my top 3 career paths and help me pick one to prioritize."),
    },
    {
      label: "Update preferences",
      Icon: SlidersHorizontal,
      onClick: () => onSendToChat("I'd like to update my job preferences."),
    },
    {
      label: "Salary expectations",
      Icon: IndianRupee,
      onClick: () => onSendToChat("Based on my profile, what could I earn in my next role?"),
    },
    {
      label: "Improve my CV",
      Icon: FileText,
      onClick: () => onSendToChat("Can you help me improve my CV?"),
    },
  ];

  const profileReady =
    profileData?.candidate?.profile_complete === true && Boolean(profileData?.resume_filename);

  const setupIncomplete =
    profileData != null &&
    (!profileData.resume_filename ||
      !profileData.candidate?.profile_complete ||
      !hasCareerPath);

  const activeVis = VISIBILITY_OPTIONS.find((o) => o.id === visibility);

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      <HomeMissionHero
        firstName={firstName}
        profile={profileData}
        hasCareerPath={hasCareerPath}
        jobCount={jobCount}
        introCount={introCount}
        intelCompleteness={intelCompleteness}
        onOpenPanel={onOpenPanel}
        onSendToChat={onSendToChat}
      />

      {showProfileBoosters && (
        <ProfileBoosters
          hasResume={hasResume ?? false}
          hasVoiceSession={hasVoiceSession ?? false}
          canApply={canApply ?? true}
          onProfileUpdated={onProfileBoosted}
        />
      )}

      <CollapsibleSection
        title="Setup & career paths"
        description="Resume, profile, and direction before matching"
        defaultOpen={setupIncomplete}
      >
        <div className="space-y-4 pt-3">
          <SetupChecklist
            profile={profileData}
            googleConnected={googleConnected}
            jobCount={jobCount}
            onOpenPanel={onOpenPanel}
          />
          {profileReady && !hasCareerPath && (
            <CareerPathOptionCards
              onSelectPath={(opt) => {
                onSendToChat(
                  `I want to prioritize the "${opt.title}" career path. Show me matching jobs for this direction.`,
                );
              }}
              onPathsReady={(n) => {
                if (n > 0) setHasCareerPath(true);
              }}
            />
          )}
        </div>
      </CollapsibleSection>

      {(intelArchetype || intelNextRole || intelCompleteness != null) && (
        <CollapsibleSection title="Career intelligence" description="Archetype and next-role signals">
          <div className="pt-3">
            <IntelligenceHero
              archetype={intelArchetype}
              nextRole={intelNextRole}
              completeness={intelCompleteness}
              onOpenIntelligence={() => onOpenPanel("profile")}
              onAskAarya={onSendToChat}
            />
          </div>
        </CollapsibleSection>
      )}

      <CollapsibleSection title="Quick ask Aarya" description="One-tap prompts for common tasks">
        <div className="flex flex-wrap gap-2 pt-3">
          {QUICK_ACTIONS.map(({ label, Icon, onClick }) => (
            <Button
              key={label}
              variant="secondary"
              size="sm"
              onClick={onClick}
              leftIcon={<Icon className="h-4 w-4 text-ink-500" strokeWidth={1.5} />}
            >
              {label}
            </Button>
          ))}
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="Voice call" description="15-minute deep dive with Aarya">
        <div className="space-y-3 pt-3">
          <p className="text-micro text-ink-600">
            Discuss jobs, salary, or positioning — same thread as chat.
          </p>
          <Link
            href="/dashboard?voice=deep&panel=jobs"
            className={cn(
              "inline-flex items-center justify-center font-medium",
              "transition-colors duration-fast ease-out-soft",
              "bg-accent text-on-accent hover:bg-accent-hover",
              "h-10 px-4 text-body gap-2 rounded-md",
            )}
          >
            <Phone className="h-3.5 w-3.5" strokeWidth={2} />
            Start call
          </Link>
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="Profile visibility" description="Who can see your profile">
        <div className="space-y-2 pt-3">
          {VISIBILITY_OPTIONS.map((opt) => {
            const isActive = visibility === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => void selectVisibility(opt.id)}
                disabled={savingVis !== null}
                className={cn(
                  "w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all duration-fast",
                  isActive
                    ? "border-accent bg-ink-50"
                    : "border-ink-200 hover:border-ink-300 hover:bg-ink-50",
                  savingVis !== null && "opacity-70",
                )}
              >
                <opt.Icon
                  className={cn("h-4 w-4 shrink-0", isActive ? "text-ink-900" : "text-ink-400")}
                  strokeWidth={1.5}
                />
                <span
                  className={cn(
                    "text-small font-medium flex-1",
                    isActive ? "text-ink-900" : "text-ink-700",
                  )}
                >
                  {opt.label}
                </span>
                {savingVis === opt.id ? (
                  <Loader2 className="h-4 w-4 text-ink-400 animate-spin" strokeWidth={1.5} />
                ) : (
                  isActive && <span className="w-2 h-2 rounded-full bg-accent" />
                )}
              </button>
            );
          })}
          {activeVis && <p className="text-micro text-ink-500 pt-1">{activeVis.hint}</p>}
        </div>
      </CollapsibleSection>
    </div>
  );
}
