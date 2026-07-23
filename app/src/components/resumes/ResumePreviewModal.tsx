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
import {
  fetchReadyApplicationKit,
  getApplicationKitForJob,
  prepareApplicationKit,
  type JobApplicationKit,
} from "@/lib/api/applicationKit";
import { useAiOperations } from "@/components/providers/AiOperationsProvider";
import {
  resolveReadyOrAccepted,
  terminalOperationError,
  waitForTrackedOperation,
} from "@/lib/operations/resolve";
import { AI_OPERATION_KINDS } from "@/lib/operations/kinds";
import { AiOperationProgress } from "@/components/operations/AiOperationProgress";

type Tab = "resume" | "cover_letter" | "interview_prep";

export function ResumePreviewModal({
  open,
  onClose,
  onAfterClose,
  resumeId,
  jobId,
  jobTitle,
  initialTab = "resume",
  coverLetter: coverLetterProp,
  interviewPrep: interviewPrepProp,
}: {
  open: boolean;
  onClose: () => void;
  /** Called after the modal closes (e.g. advance saved-job queue). */
  onAfterClose?: () => void;
  resumeId: string | null;
  jobId: string | null;
  jobTitle?: string | null;
  initialTab?: Tab;
  coverLetter?: string | null;
  interviewPrep?: string | null;
}) {
  const { toast } = useToast();
  const {
    trackAndWait,
    waitForOperation,
    operations,
    cancelOperation,
    retryOperation,
  } = useAiOperations();
  const [tab, setTab] = useState<Tab>("resume");
  const [html, setHtml] = useState<string | null>(null);
  const [kit, setKit] = useState<JobApplicationKit | null>(null);
  const [effectiveResumeId, setEffectiveResumeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);
  const [activeOpId, setActiveOpId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let kitData = jobId ? await getApplicationKitForJob(jobId).catch(() => null) : null;
      let resolvedResumeId = resumeId ?? kitData?.tailored_resume_id ?? null;

      // Older kits may lack a resume (generated before always-on tailoring). Re-prepare once.
      if (!resolvedResumeId && jobId) {
        const outcome = await prepareApplicationKit(jobId);
        if (outcome.status === "accepted") {
          setActiveOpId(outcome.operation.operation_id);
        }
        const prepared = await resolveReadyOrAccepted(
          outcome,
          trackAndWait,
          () => fetchReadyApplicationKit(jobId),
          { kind: AI_OPERATION_KINDS.applicationKit },
        );
        kitData = {
          id: prepared.kit_id ?? kitData?.id ?? "",
          job_id: jobId,
          job_title: prepared.job?.title ?? kitData?.job_title ?? null,
          company_name: prepared.job?.company_name ?? kitData?.company_name ?? null,
          cover_letter: prepared.cover_letter,
          interview_prep: prepared.interview_prep,
          tailored_resume_id: prepared.resume?.resume_id ?? null,
          mock_interview_id: prepared.mock_interview?.mock_interview_id ?? null,
          created_at: kitData?.created_at ?? new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        resolvedResumeId = prepared.resume?.resume_id ?? null;
        setActiveOpId(null);
      }

      const resumeHtml = resolvedResumeId
        ? await fetchTailoredResumeHtml(resolvedResumeId)
        : null;

      setEffectiveResumeId(resolvedResumeId);
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
  }, [resumeId, jobId, initialTab, coverLetterProp, interviewPrepProp, trackAndWait]);

  const handleRetryActive = useCallback(async () => {
    if (!activeOpId || !jobId) return;
    setLoading(true);
    setError(null);
    try {
      const replacement = await retryOperation(activeOpId);
      setActiveOpId(replacement.id);
      const terminal = await waitForTrackedOperation(
        replacement,
        waitForOperation,
      );
      if (terminal.status !== "succeeded") {
        throw terminalOperationError(terminal);
      }
      const prepared = await fetchReadyApplicationKit(jobId);
      const resolvedResumeId = prepared.resume?.resume_id ?? null;
      setKit({
        id: prepared.kit_id ?? "",
        job_id: jobId,
        job_title: prepared.job?.title ?? null,
        company_name: prepared.job?.company_name ?? null,
        cover_letter: prepared.cover_letter,
        interview_prep: prepared.interview_prep,
        tailored_resume_id: resolvedResumeId,
        mock_interview_id: prepared.mock_interview?.mock_interview_id ?? null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      setEffectiveResumeId(resolvedResumeId);
      if (resolvedResumeId) {
        setHtml(await fetchTailoredResumeHtml(resolvedResumeId));
      }
      setActiveOpId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load preview");
    } finally {
      setLoading(false);
    }
  }, [activeOpId, jobId, retryOperation, waitForOperation]);

  useEffect(() => {
    if (open) void load();
    else {
      setHtml(null);
      setKit(null);
      setEffectiveResumeId(null);
      setError(null);
    }
  }, [open, load]);

  const handleDownload = async () => {
    if (!effectiveResumeId || downloading) return;
    setDownloading("pdf");
    try {
      await downloadTailoredResume(effectiveResumeId);
    } catch {
      toast.error("Couldn't open the resume for download");
    } finally {
      setDownloading(null);
    }
  };

  const handleDocx = async () => {
    if (!effectiveResumeId || downloading) return;
    setDownloading("docx");
    try {
      await downloadTailoredResumeDocx(effectiveResumeId);
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

  const handleClose = () => {
    onClose();
    onAfterClose?.();
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
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
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-ink-500">
          {activeOpId && operations[activeOpId] ? (
            <div className="w-full max-w-sm">
              <AiOperationProgress
                compact
                operation={operations[activeOpId]}
                onCancel={() => {
                  void cancelOperation(activeOpId).catch(() => undefined);
                }}
                onRetry={() => {
                  void handleRetryActive();
                }}
              />
            </div>
          ) : (
            <div className="flex items-center">
              <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading preview…
            </div>
          )}
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
        <Button variant="ghost" onClick={handleClose}>
          Close
        </Button>
        <Button
          variant="secondary"
          onClick={() => void handleDocx()}
          disabled={!effectiveResumeId || downloading !== null}
          loading={downloading === "docx"}
          leftIcon={<Download className="h-3.5 w-3.5" />}
        >
          Download Word
        </Button>
        <Button
          variant="primary"
          onClick={() => void handleDownload()}
          disabled={!effectiveResumeId || downloading !== null}
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
