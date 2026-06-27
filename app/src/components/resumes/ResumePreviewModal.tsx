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
import { Download, Loader2 } from "lucide-react";
import { Button, Modal, ModalFooter, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";
import { downloadTailoredResume, fetchTailoredResumeHtml } from "@/lib/api/tailored";
import { getApplicationKitForJob, type JobApplicationKit } from "@/lib/api/applicationKit";

type Tab = "resume" | "cover_letter" | "interview_prep";

export function ResumePreviewModal({
  open,
  onClose,
  resumeId,
  jobId,
  jobTitle,
}: {
  open: boolean;
  onClose: () => void;
  resumeId: string | null;
  jobId: string | null;
  jobTitle?: string | null;
}) {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>("resume");
  const [html, setHtml] = useState<string | null>(null);
  const [kit, setKit] = useState<JobApplicationKit | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

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
      // Default to the first tab that actually has content.
      setTab(resumeHtml ? "resume" : kitData?.cover_letter ? "cover_letter" : "resume");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load preview");
    } finally {
      setLoading(false);
    }
  }, [resumeId, jobId]);

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
    setDownloading(true);
    try {
      await downloadTailoredResume(resumeId);
    } catch {
      toast.error("Couldn't open the resume for download");
    } finally {
      setDownloading(false);
    }
  };

  const tabs: { key: Tab; label: string; available: boolean }[] = [
    { key: "resume", label: "Resume", available: !!html },
    { key: "cover_letter", label: "Cover letter", available: !!kit?.cover_letter },
    { key: "interview_prep", label: "Interview prep", available: !!kit?.interview_prep },
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
              <iframe
                title="Tailored resume preview"
                srcDoc={html}
                sandbox="allow-same-origin"
                className="w-full h-[60vh] rounded-lg border border-ink-200 bg-white"
              />
            ) : (
              <p className="py-12 text-center text-small text-ink-500">
                No tailored resume for this role yet.
              </p>
            ))}

          {tab === "cover_letter" && (
            <p className="whitespace-pre-wrap text-small text-ink-700 leading-relaxed max-h-[60vh] overflow-y-auto">
              {kit?.cover_letter || "No cover letter for this role yet."}
            </p>
          )}

          {tab === "interview_prep" && (
            <p className="whitespace-pre-wrap text-small text-ink-700 leading-relaxed max-h-[60vh] overflow-y-auto">
              {kit?.interview_prep || "No interview prep for this role yet."}
            </p>
          )}
        </div>
      )}

      <ModalFooter>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
        <Button
          variant="primary"
          onClick={() => void handleDownload()}
          disabled={!resumeId || downloading}
          leftIcon={
            downloading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )
          }
        >
          Download resume
        </Button>
      </ModalFooter>
    </Modal>
  );
}
