"use client";

import Link from "next/link";
import { useState } from "react";
import { Briefcase, Copy, Download, FileText, GraduationCap, Check } from "@/components/brand/icons";
import type { ApplicationKit } from "@/lib/api/applicationKit";
import { apiAuthFetch } from "@/lib/api/auth-fetch";
import { cn } from "@/lib/utils";

type ApplicationKitCardsProps = {
  kits: ApplicationKit[];
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

export function ApplicationKitCards({ kits }: ApplicationKitCardsProps) {
  if (!kits.length) return null;

  const downloadResume = async (path: string | null) => {
    if (!path) return;
    const res = await apiAuthFetch(path);
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "tailored-resume.html";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="w-full max-w-xl space-y-3">
      <p className="text-small font-medium text-ink-600">
        Application kit{kits.length !== 1 ? "s" : ""} ready — saved to your list
      </p>
      {kits.map((kit) => {
        const job = kit.job;
        const title = job.title ?? "Role";
        const company = job.company_name ?? "Company";
        return (
          <div
            key={job.job_id}
            className="rounded-xl border border-ink-200 bg-paper-1 p-4 space-y-3 shadow-sm"
          >
            <div className="flex items-start gap-2">
              <Briefcase className="h-4 w-4 mt-0.5 text-ink-500 shrink-0" />
              <div className="min-w-0">
                <p className="text-small font-semibold text-ink-900 truncate">{title}</p>
                <p className="text-micro text-ink-500">{company}</p>
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                disabled={!kit.resume.download_path}
                onClick={() => void downloadResume(kit.resume.download_path)}
                className={cn(
                  "flex items-center gap-2 rounded-lg border border-ink-200 px-3 py-2 text-left text-small",
                  kit.resume.download_path
                    ? "hover:bg-ink-50"
                    : "opacity-50 cursor-not-allowed"
                )}
              >
                <Download className="h-4 w-4 shrink-0 text-accent" />
                <span>Tailored resume</span>
              </button>

              <details className="rounded-lg border border-ink-200 px-3 py-2">
                <summary className="flex cursor-pointer items-center gap-2 text-small list-none">
                  <FileText className="h-4 w-4 shrink-0 text-accent" />
                  <span>Cover letter</span>
                </summary>
                <div className="mt-2 space-y-2">
                  <p className="text-micro text-ink-600 whitespace-pre-wrap max-h-40 overflow-y-auto">
                    {kit.cover_letter}
                  </p>
                  <CopyButton text={kit.cover_letter} label="Copy letter" />
                </div>
              </details>

              <details className="rounded-lg border border-ink-200 px-3 py-2 sm:col-span-2">
                <summary className="flex cursor-pointer items-center gap-2 text-small list-none">
                  <GraduationCap className="h-4 w-4 shrink-0 text-accent" />
                  <span>Interview prep</span>
                </summary>
                <div className="mt-2 space-y-2">
                  <p className="text-micro text-ink-600 whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {kit.interview_prep}
                  </p>
                  <CopyButton text={kit.interview_prep} label="Copy prep" />
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
          </div>
        );
      })}
    </div>
  );
}
