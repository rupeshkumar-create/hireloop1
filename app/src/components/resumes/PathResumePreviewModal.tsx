"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "@/components/brand/icons";
import { Button, Modal, ModalFooter, useToast } from "@/components/ui";
import {
  downloadCareerPathResumeDocx,
  downloadCareerPathResumePdf,
  fetchCareerPathResumePreview,
} from "@/lib/api/career";

export function PathResumePreviewModal({
  open,
  onClose,
  resumeId,
  pathTitle,
}: {
  open: boolean;
  onClose: () => void;
  resumeId: string | null;
  pathTitle?: string | null;
}) {
  const { toast } = useToast();
  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);

  const load = useCallback(async () => {
    if (!resumeId) return;
    setLoading(true);
    setError(null);
    try {
      setHtml(await fetchCareerPathResumePreview(resumeId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load preview");
    } finally {
      setLoading(false);
    }
  }, [resumeId]);

  useEffect(() => {
    if (open && resumeId) void load();
    else {
      setHtml(null);
      setError(null);
    }
  }, [open, resumeId, load]);

  async function handlePdf() {
    if (!resumeId) return;
    setDownloading("pdf");
    try {
      await downloadCareerPathResumePdf(resumeId);
    } catch {
      toast.error("Couldn't open PDF download");
    } finally {
      setDownloading(null);
    }
  }

  async function handleDocx() {
    if (!resumeId) return;
    setDownloading("docx");
    try {
      await downloadCareerPathResumeDocx(resumeId);
    } catch {
      toast.error("Couldn't download Word file");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Career path resume"
      description={pathTitle ?? undefined}
      size="lg"
      className="max-w-4xl"
    >
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
      ) : html ? (
        <iframe
          title="Career path resume preview"
          srcDoc={html}
          sandbox="allow-same-origin"
          className="w-full h-[60vh] rounded-lg border border-ink-200 bg-white"
        />
      ) : (
        <p className="py-12 text-center text-small text-ink-500">No resume to preview.</p>
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
          onClick={() => void handlePdf()}
          disabled={!resumeId || downloading !== null}
          loading={downloading === "pdf"}
          leftIcon={<Download className="h-3.5 w-3.5" />}
        >
          Download PDF
        </Button>
      </ModalFooter>
    </Modal>
  );
}
