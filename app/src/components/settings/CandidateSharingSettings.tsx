"use client";

import { useCallback, useEffect, useState } from "react";
import { Copy, ExternalLink, FileText, Shield } from "@/components/brand/icons";
import {
  fetchCareerPathResumes,
  generateCareerPathResumes,
  type CareerPathResume,
} from "@/lib/api/career";
import {
  fetchMyProfile,
  publishPublicProfile,
  updateMyProfile,
  type DisplayCurrency,
  type MyProfileData,
} from "@/lib/api/profile";
import { Button, Card, CardBody, CardFooter, CardHeader, useToast } from "@/components/ui";
import { PathResumePreviewModal } from "@/components/resumes/PathResumePreviewModal";
import { cn } from "@/lib/utils";

const CURRENCY_OPTIONS: { id: DisplayCurrency; label: string }[] = [
  { id: "auto", label: "Auto (from country / resume)" },
  { id: "INR", label: "Indian Rupee (₹)" },
  { id: "USD", label: "US Dollar ($)" },
  { id: "GBP", label: "British Pound (£)" },
  { id: "EUR", label: "Euro (€)" },
];

export function CandidateSharingSettings() {
  const { toast } = useToast();
  const [profile, setProfile] = useState<MyProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [currency, setCurrency] = useState<DisplayCurrency>("auto");
  const [savingCurrency, setSavingCurrency] = useState(false);
  const [hideContact, setHideContact] = useState(true);
  const [shareRecruiters, setShareRecruiters] = useState(true);
  const [published, setPublished] = useState(true);
  const [publicUrl, setPublicUrl] = useState<string | null>(null);
  const [savingPrivacy, setSavingPrivacy] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [pathResumes, setPathResumes] = useState<CareerPathResume[]>([]);
  const [generatingResumes, setGeneratingResumes] = useState(false);
  const [previewResume, setPreviewResume] = useState<CareerPathResume | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, resumes] = await Promise.all([
        fetchMyProfile({ force: true }),
        fetchCareerPathResumes().catch(() => [] as CareerPathResume[]),
      ]);
      setProfile(p);
      setCurrency((p.candidate?.display_currency as DisplayCurrency) ?? "auto");
      setHideContact(p.candidate?.hide_contact_public ?? true);
      setShareRecruiters(p.candidate?.share_with_recruiters ?? true);
      setPublished(p.candidate?.public_profile_enabled ?? true);
      const rel = p.candidate?.public_profile_url;
      setPublicUrl(rel ? `${typeof window !== "undefined" ? window.location.origin : ""}${rel}` : null);
      setPathResumes(resumes);
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't load sharing settings");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveCurrency() {
    setSavingCurrency(true);
    try {
      await updateMyProfile({ display_currency: currency });
      toast.success("Currency preference saved");
      await load();
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't save currency");
    } finally {
      setSavingCurrency(false);
    }
  }

  async function savePrivacy() {
    setSavingPrivacy(true);
    try {
      await updateMyProfile({
        hide_contact_public: hideContact,
        share_with_recruiters: shareRecruiters,
        public_profile_enabled: published,
      });
      toast.success("Privacy settings saved");
      await load();
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't save privacy settings");
    } finally {
      setSavingPrivacy(false);
    }
  }

  async function handlePublish() {
    setPublishing(true);
    try {
      const result = await publishPublicProfile();
      const full = `${window.location.origin}${result.public_profile_url}`;
      setPublicUrl(full);
      setPublished(true);
      toast.success("Public profile is live");
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't publish profile");
    } finally {
      setPublishing(false);
    }
  }

  async function handleGenerateResumes() {
    setGeneratingResumes(true);
    try {
      const resumes = await generateCareerPathResumes();
      setPathResumes(resumes);
      toast.success("Career-path resumes generated");
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't generate resumes");
    } finally {
      setGeneratingResumes(false);
    }
  }

  function copyLink() {
    if (!publicUrl) return;
    void navigator.clipboard.writeText(publicUrl);
    toast.success("Link copied");
  }

  const resolved = profile?.candidate?.display_currency_resolved ?? "INR";

  if (loading) {
    return (
      <Card>
        <CardBody>
          <p className="text-small text-ink-500">Loading sharing settings…</p>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Currency"
          description="How salaries and compensation are shown across jobs and your profile."
        />
        <CardBody className="space-y-3 !pt-0">
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value as DisplayCurrency)}
            className="h-10 w-full rounded-md border border-ink-100 bg-paper-1 px-3 text-small text-ink-900 outline-none focus:ring-2 focus:ring-accent-ring"
          >
            {CURRENCY_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id}>
                {opt.label}
              </option>
            ))}
          </select>
          <p className="text-micro text-ink-500">
            {currency === "auto"
              ? `Auto resolves to ${resolved} from your market and resume location.`
              : `Salaries will display in ${currency}.`}
          </p>
        </CardBody>
        <CardFooter>
          <Button variant="primary" size="sm" loading={savingCurrency} onClick={() => void saveCurrency()}>
            Save currency
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader
          title="Career path resumes"
          description="Private ATS-style resumes for each path direction. Preview and download — never shown on your public profile."
        />
        <CardBody className="space-y-3 !pt-0">
          {pathResumes.length === 0 ? (
            <p className="text-small text-ink-500">
              Generate your career path first, then create path-specific resumes here.
            </p>
          ) : (
            <ul className="space-y-2">
              {pathResumes.map((r) => (
                <li
                  key={r.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-ink-100 bg-paper-1 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-small font-medium text-ink-900 truncate">{r.path_title}</p>
                    <p className="text-micro text-ink-500 capitalize">{r.status}</p>
                  </div>
                  {r.status === "ready" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      leftIcon={<FileText className="h-3.5 w-3.5" />}
                      onClick={() => setPreviewResume(r)}
                    >
                      Preview
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
        <CardFooter>
          <Button
            variant="secondary"
            size="sm"
            loading={generatingResumes}
            onClick={() => void handleGenerateResumes()}
          >
            {generatingResumes ? "Generating…" : "Generate all 3 resumes"}
          </Button>
        </CardFooter>
      </Card>

      <PathResumePreviewModal
        open={previewResume !== null}
        onClose={() => setPreviewResume(null)}
        resumeId={previewResume?.id ?? null}
        pathTitle={previewResume?.path_title}
      />

      <Card>
        <CardHeader
          title="Public profile & sharing"
          description="Control who can see your profile and contact details."
        />
        <CardBody className="space-y-4 !pt-0">
          <ToggleRow
            label="Hide email & phone on public page"
            description="Your name, email, phone, location, and LinkedIn stay private. Visitors see experience and skills only. The share link uses an anonymous URL."
            checked={hideContact}
            onChange={setHideContact}
          />
          <ToggleRow
            label="Share with Hireschema recruiters"
            description="Registered recruiters on Hireschema can discover your profile in search. Off = hidden from recruiter inbox."
            checked={shareRecruiters}
            onChange={setShareRecruiters}
          />
          <ToggleRow
            label="Publish public profile link"
            description="Anyone with the link can view your published page."
            checked={published}
            onChange={setPublished}
          />
          {publicUrl && published && (
            <div className="rounded-lg border border-ink-100 bg-ink-50/50 px-3 py-2.5 space-y-2">
              <p className="text-micro font-medium text-ink-700 flex items-center gap-1.5">
                <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
                Shareable link
              </p>
              <p className="text-micro text-ink-600 break-all">{publicUrl}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" leftIcon={<Copy className="h-3.5 w-3.5" />} onClick={copyLink}>
                  Copy link
                </Button>
                <a
                  href={publicUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(
                    "inline-flex items-center gap-1.5 h-8 px-3 text-small rounded-md",
                    "border border-ink-100 text-ink-800 hover:bg-paper-1"
                  )}
                >
                  <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
                  Preview
                </a>
              </div>
            </div>
          )}
          {!published && (
            <p className="text-micro text-ink-500 flex items-start gap-1.5">
              <Shield className="h-3.5 w-3.5 shrink-0 mt-0.5" strokeWidth={1.5} />
              Publish to get a link you can share on LinkedIn or with hiring managers.
            </p>
          )}
        </CardBody>
        <CardFooter className="flex flex-wrap gap-2">
          <Button variant="primary" size="sm" loading={savingPrivacy} onClick={() => void savePrivacy()}>
            Save privacy
          </Button>
          {!published && (
            <Button variant="secondary" size="sm" loading={publishing} onClick={() => void handlePublish()}>
              Publish & get link
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <div className="min-w-0">
        <p className="text-small font-medium text-ink-900">{label}</p>
        <p className="text-micro text-ink-500">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-5 w-9 rounded-full transition-colors shrink-0",
          checked ? "bg-accent" : "bg-ink-100"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-paper-1 shadow-1 transition-transform",
            checked ? "translate-x-[18px]" : "translate-x-0.5"
          )}
        />
      </button>
    </div>
  );
}
