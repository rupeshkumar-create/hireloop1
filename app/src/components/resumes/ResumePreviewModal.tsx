"use client";

/**
 * ResumePreviewModal — in-app preview of an application kit.
 *
 * Shows the tailored resume (rendered HTML, in a sandboxed iframe) plus the
 * cover letter and interview prep, so the candidate can review everything Aarya
 * generated without downloading first. Resume HTML and kit text are fetched with
 * the bearer token (the endpoints are auth-protected).
 */

import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "@/components/brand/icons";
import { Button, Modal, ModalFooter, useToast } from "@/components/ui";
import { RichMarkdown } from "@/components/ui/RichMarkdown";
import { cn } from "@/lib/utils";
import {
  downloadTailoredResume,
  downloadTailoredResumeDocx,
  fetchTailoredResumeHtml,
} from "@/lib/api/tailored";
import { getApplicationKitForJob, type JobApplicationKit } from "@/lib/api/applicationKit";

type Tab = "resume" | "cover_letter" | "interview_prep";

export function ResumePreviewModal({
  open,
  onClose,
  resumeId,
  jobId,
  jobTitle,
  initialTab = "resume",
  coverLetter: coverLetterProp,
  interviewPrep: interviewPrepProp,
}: {
  open: boolean;
  onClose: () => void;
  resumeId: string | null;
  jobId: string | null;
  jobTitle?: string | null;
  initialTab?: Tab;
  coverLetter?: string | null;
  interviewPrep?: string | null;
}) {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>("resume");
  const [html, setHtml] = useState<string | null>(null);
  const [kit, setKit] = useState<JobApplicationKit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [resumeHtml, kitData] = await Promise.all([
        resumeId ? fetchTailoredResumeHtml(resumeId) : Promise.resolve(null),
        jobId ? getApplicationKitForJob(jobId).catch(() => null) : Promise.resolve(null),
      ]);
      setHtml(resumeHtml);
      setKit(kitData);
      const cover = coverLetterProp ?? kitData?.cover_letter ?? null;
      const prep = interviewPrepProp ?? kitData?.interview_prep ?? null;
      const preferred =
        initialTab === "cover_letter" && cover
          ? "cover_letter"
          : initialTab === "interview_prep" && prep
            ? "interview_prep"
            : resumeHtml
              ? "resume"
              : cover
                ? "cover_letter"
                : prep
                  ? "interview_prep"
                  : "resume";
      setTab(preferred);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load preview");
    } finally {
      setLoading(false);
    }
  }, [resumeId, jobId, initialTab, coverLetterProp, interviewPrepProp]);

  useEffect(() => {
    if (open) void load();
    else {
      setHtml(null);
      setKit(null);
      setError(null);
    }
  }, [open, load]);

  const handleDownload = async () => {
    if (!resumeId || downloading) return;
    setDownloading("pdf");
    try {
      await downloadTailoredResume(resumeId);
    } catch {
      toast.error("Couldn't open the resume for download");
    } finally {
      setDownloading(null);
    }
  };

  const handleDocx = async () => {
    if (!resumeId || downloading) return;
    setDownloading("docx");
    try {
      await downloadTailoredResumeDocx(resumeId);
    } catch {
      toast.error("Couldn't download the Word file");
    } finally {
      setDownloading(null);
    }
  };

  const coverLetter = coverLetterProp ?? kit?.cover_letter ?? null;
  const interviewPrep = interviewPrepProp ?? kit?.interview_prep ?? null;

  const tabs: { key: Tab; label: string; available: boolean }[] = [
    { key: "resume", label: "Resume (PDF)", available: !!html },
    { key: "cover_letter", label: "Cover letter", available: !!coverLetter },
    { key: "interview_prep", label: "Interview prep", available: !!interviewPrep },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Application kit"
      description={jobTitle ?? kit?.job_title ?? undefined}
      size="lg"
      className="max-w-4xl"
    >
      {/* Tabs */}
      <div className="flex gap-1 border-b border-ink-100 mb-3">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            disabled={!t.available}
            onClick={() => setTab(t.key)}
            className={cn(
              "px-3 py-2 text-small font-medium -mb-px border-b-2 transition-colors",
              tab === t.key
                ? "border-accent text-ink-900"
                : "border-transparent text-ink-500 hover:text-ink-900",
              !t.available && "opacity-40 cursor-not-allowed"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-ink-500">
          <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading preview…
        </div>
      ) : error ? (
        <div className="py-12 text-center text-small text-ink-500">
          {error}
          <div className="mt-3">
            <Button size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        </div>
      ) : (
        <div className="min-h-[420px]">
          {tab === "resume" &&
            (html ? (
              <div className="space-y-2">
                <p className="text-micro text-ink-500">
                  This matches the PDF you get when you save — review formatting before downloading.
                </p>
                <iframe
                  title="Tailored resume preview"
                  srcDoc={html}
                  sandbox="allow-same-origin"
                  className="w-full h-[60vh] rounded-lg border border-ink-200 bg-white"
                />
              </div>
            ) : (
              <p className="py-12 text-center text-small text-ink-500">
                No tailored resume for this role yet.
              </p>
            ))}

          {tab === "cover_letter" && (
            <div className="max-h-[60vh] overflow-y-auto rounded-lg border border-ink-100 bg-paper-1 p-5 sm:p-6">
              {coverLetter ? (
                <RichMarkdown content={coverLetter} variant="document" />
              ) : (
                <p className="py-8 text-center text-small text-ink-500">
                  No cover letter for this role yet.
                </p>
              )}
            </div>
          )}

          {tab === "interview_prep" && (
            <div className="max-h-[60vh] overflow-y-auto rounded-lg border border-ink-100 bg-paper-1 p-5 sm:p-6">
              {interviewPrep ? (
                <RichMarkdown content={interviewPrep} variant="document" />
              ) : (
                <p className="py-8 text-center text-small text-ink-500">
                  No interview prep for this role yet.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      <ModalFooter>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
        <Button
          variant="secondary"
          onClick={() => void handleDocx()}
          disabled={!resumeId || downloading !== null}
          loading={downloading === "docx"}
          leftIcon={<Download className="h-3.5 w-3.5" />}
        >
          Download Word
        </Button>
        <Button
          variant="primary"
          onClick={() => void handleDownload()}
          disabled={!resumeId || downloading !== null}
          leftIcon={
            downloading === "pdf" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )
          }
        >
          Download PDF
        </Button>
      </ModalFooter>
    </Modal>
  );
}
