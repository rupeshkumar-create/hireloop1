"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Briefcase,
  Copy,
  Download,
  Eye,
  FileText,
  GraduationCap,
  Check,
} from "@/components/brand/icons";
import type { ApplicationKit } from "@/lib/api/applicationKit";
import { downloadTailoredResume } from "@/lib/api/tailored";
import { ResumePreviewModal } from "@/components/resumes/ResumePreviewModal";
import { RichMarkdown } from "@/components/ui/RichMarkdown";
import { useToast } from "@/components/ui";
import { BTN_PRIMARY, BTN_GHOST } from "@/lib/button-classes";
import { cn } from "@/lib/utils";

type ApplicationKitCardsProps = {
  kits: ApplicationKit[];
};

type PreviewState = {
  resumeId: string | null;
  jobId: string;
  jobTitle: string;
  tab: "resume" | "cover_letter" | "interview_prep";
  coverLetter: string;
  interviewPrep: string;
};

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      }}
      className="inline-flex items-center gap-1 text-micro font-medium text-ink-600 hover:text-ink-900"
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {copied ? "Copied" : label}
    </button>
  );
}

function filenamePart(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "application-kit";
}

function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function DownloadTextButton({
  text,
  filename,
  label,
}: {
  text: string;
  filename: string;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={() => downloadTextFile(filename, text)}
      className="inline-flex items-center gap-1 text-micro font-medium text-ink-600 hover:text-ink-900"
    >
      <Download className="h-3 w-3" />
      {label}
    </button>
  );
}

function PreviewButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        BTN_GHOST,
        "flex items-center gap-2 px-3 py-2 text-left text-small",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <Eye className="h-4 w-4 shrink-0 text-accent" />
      <span>{label}</span>
    </button>
  );
}

export function ApplicationKitCards({ kits }: ApplicationKitCardsProps) {
  const { toast } = useToast();
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [downloadingResumeId, setDownloadingResumeId] = useState<string | null>(null);

  if (!kits.length) return null;

  return (
    <>
      <div className="w-full space-y-3">
        <p className="text-small font-medium text-ink-600">
          Application kit{kits.length !== 1 ? "s" : ""} ready — saved to your list
        </p>
        {kits.map((kit) => {
          const job = kit.job;
          const title = job.title ?? "Role";
          const company = job.company_name ?? "Company";
          const resumeId = kit.resume.resume_id;
          const resumeReady =
            kit.resume.status === "ready" && Boolean(resumeId);
          const filenameBase = filenamePart(`${title}-${company}`);

          const openPreview = (tab: PreviewState["tab"]) => {
            setPreview({
              resumeId: resumeReady ? resumeId : null,
              jobId: job.job_id,
              jobTitle: title,
              tab,
              coverLetter: kit.cover_letter,
              interviewPrep: kit.interview_prep,
            });
          };

          const downloadResume = async () => {
            if (!resumeId || downloadingResumeId) return;
            setDownloadingResumeId(resumeId);
            try {
              await downloadTailoredResume(resumeId);
            } catch {
              toast.error("Couldn't open the resume for download");
            } finally {
              setDownloadingResumeId(null);
            }
          };

          return (
            <div
              key={job.job_id}
              className="rounded-xl border border-ink-200 bg-paper-1 p-4 space-y-3 shadow-sm"
            >
              <div className="flex items-start gap-2">
                <Briefcase className="h-4 w-4 mt-0.5 text-ink-500 shrink-0" />
                <div className="min-w-0">
                  <p className="text-small font-semibold text-ink-900 truncate">
                    {title}
                  </p>
                  <p className="text-micro text-ink-500">{company}</p>
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                <PreviewButton
                  label="Preview resume (PDF)"
                  disabled={!resumeReady}
                  onClick={() => openPreview("resume")}
                />

                <button
                  type="button"
                  disabled={!resumeReady || downloadingResumeId === resumeId}
                  onClick={() => void downloadResume()}
                  className={cn(
                    BTN_GHOST,
                    "flex items-center gap-2 px-3 py-2 text-left text-small",
                    (!resumeReady || downloadingResumeId === resumeId) &&
                      "opacity-50 cursor-not-allowed",
                  )}
                >
                  <Download className="h-4 w-4 shrink-0 text-accent" />
                  <span>
                    {downloadingResumeId === resumeId
                      ? "Preparing download…"
                      : "Download resume"}
                  </span>
                </button>

                <PreviewButton
                  label="Preview cover letter"
                  disabled={!kit.cover_letter}
                  onClick={() => openPreview("cover_letter")}
                />

                <details className="rounded-lg border border-ink-200 px-3 py-2 sm:col-span-2">
                  <summary className="flex cursor-pointer items-center gap-2 text-small list-none">
                    <GraduationCap className="h-4 w-4 shrink-0 text-accent" />
                    <span>Interview prep</span>
                  </summary>
                  <div className="mt-2 space-y-2">
                    <div className="max-h-48 overflow-y-auto rounded-lg border border-ink-100 bg-paper-0/80 p-3">
                      <RichMarkdown content={kit.interview_prep} variant="document" />
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => openPreview("interview_prep")}
                        className="inline-flex items-center gap-1 text-micro font-medium text-ink-600 hover:text-ink-900"
                      >
                        <Eye className="h-3 w-3" />
                        Full preview
                      </button>
                      <DownloadTextButton
                        text={kit.interview_prep}
                        filename={`${filenameBase}-interview-prep.md`}
                        label="Download prep"
                      />
                      <CopyButton text={kit.interview_prep} label="Copy prep" />
                    </div>
                  </div>
                </details>

                {kit.mock_interview?.path && (
                  <Link
                    href={kit.mock_interview.path}
                    className={cn(BTN_PRIMARY, "flex gap-2 px-3 py-2 text-small sm:col-span-2")}
                  >
                    <GraduationCap className="h-4 w-4 shrink-0" />
                    Start mock interview
                  </Link>
                )}

                {kit.apply_url && (
                  <a
                    href={kit.apply_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(BTN_GHOST, "flex items-center justify-center gap-2 px-3 py-2 text-small sm:col-span-2")}
                  >
                    Open apply link
                  </a>
                )}
              </div>

              {kit.cover_letter && (
                <div className="flex flex-wrap items-center gap-3 text-micro text-ink-500">
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <DownloadTextButton
                    text={kit.cover_letter}
                    filename={`${filenameBase}-cover-letter.md`}
                    label="Download cover letter"
                  />
                  <CopyButton text={kit.cover_letter} label="Copy cover letter" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <ResumePreviewModal
        open={!!preview}
        onClose={() => setPreview(null)}
        resumeId={preview?.resumeId ?? null}
        jobId={preview?.jobId ?? null}
        jobTitle={preview?.jobTitle}
        initialTab={preview?.tab}
        coverLetter={preview?.coverLetter}
        interviewPrep={preview?.interviewPrep}
      />
    </>
  );
}
