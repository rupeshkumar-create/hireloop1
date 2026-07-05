"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Briefcase,
  Copy,
  Eye,
  FileText,
  GraduationCap,
  Check,
} from "@/components/brand/icons";
import type { ApplicationKit } from "@/lib/api/applicationKit";
import { ResumePreviewModal } from "@/components/resumes/ResumePreviewModal";
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
        "flex items-center gap-2 rounded-lg border border-ink-200 px-3 py-2 text-left text-small",
        disabled ? "opacity-50 cursor-not-allowed" : "hover:bg-ink-50",
      )}
    >
      <Eye className="h-4 w-4 shrink-0 text-accent" />
      <span>{label}</span>
    </button>
  );
}

export function ApplicationKitCards({ kits }: ApplicationKitCardsProps) {
  const [preview, setPreview] = useState<PreviewState | null>(null);

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
                    <p className="text-micro text-ink-600 whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {kit.interview_prep}
                    </p>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => openPreview("interview_prep")}
                        className="inline-flex items-center gap-1 text-micro font-medium text-ink-600 hover:text-ink-900"
                      >
                        <Eye className="h-3 w-3" />
                        Full preview
                      </button>
                      <CopyButton text={kit.interview_prep} label="Copy prep" />
                    </div>
                  </div>
                </details>

                {kit.mock_interview?.path && (
                  <Link
                    href={kit.mock_interview.path}
                    className="flex items-center gap-2 rounded-lg border border-accent bg-accent px-3 py-2 text-small text-on-accent hover:bg-accent-hover sm:col-span-2"
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
                    className="flex items-center justify-center gap-2 rounded-lg border border-ink-200 px-3 py-2 text-small font-medium hover:bg-ink-50 sm:col-span-2"
                  >
                    Open apply link
                  </a>
                )}
              </div>

              {kit.cover_letter && (
                <div className="flex items-center gap-2 text-micro text-ink-500">
                  <FileText className="h-3.5 w-3.5 shrink-0" />
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
