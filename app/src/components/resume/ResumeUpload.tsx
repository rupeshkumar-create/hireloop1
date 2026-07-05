"use client";

/**
 * ResumeUpload — drag-and-drop + click-to-browse resume uploader.
 *
 * Flow:
 *  1. User drags or selects a PDF/DOCX (max 10MB)
 *  2. POST /api/v1/resumes/upload → returns ParsedResume
 *  3. Show parsed preview (name, skills, experience)
 *  4. "Apply to profile" → POST /api/v1/resumes/{id}/apply-to-profile
 *  5. Profile fields auto-filled
 */

import { useState, useRef, useCallback } from "react";
import { DIRECT_API_URL } from "@/lib/api/base-url";
import { ApiUnreachableError, apiAuthFetch } from "@/lib/api/auth-fetch";
import { invalidateProfileCache } from "@/lib/api/profile";
import { cn } from "@/lib/utils";

interface ParsedResume {
  full_name?: string;
  current_title?: string;
  current_company?: string;
  years_experience?: number;
  skills: string[];
  location_city?: string;
  location_state?: string;
  summary?: string;
}

interface UploadResponse {
  resume_id: string;
  file_path: string;
  parsed: ParsedResume;
  message: string;
}

type UploadState = "idle" | "dragging" | "uploading" | "parsed" | "applying" | "done" | "error";

interface ResumeUploadProps {
  onDone?: (resumeId: string, parsed: ParsedResume) => void;
  autoApply?: boolean;
  /** Filename of the résumé already on file — shows a "current file + Replace" view. */
  currentFileName?: string | null;
}

export function ResumeUpload({
  onDone,
  autoApply = false,
  currentFileName = null,
}: ResumeUploadProps) {
  const [state, setState] = useState<UploadState>("idle");
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [showDropzone, setShowDropzone] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const applyResumeToProfile = useCallback(async (result: UploadResponse) => {
    try {
      // replace: a deliberately uploaded CV is the source of truth — the
      // profile overview must follow it, not keep the old values.
      const res = await apiAuthFetch(
        `/api/v1/resumes/${result.resume_id}/apply-to-profile?mode=replace`,
        { method: "POST" }
      );
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Failed to apply to profile");
      }
      invalidateProfileCache();
      setState("done");
      onDone?.(result.resume_id, result.parsed);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to apply");
      setState("error");
    }
  }, [onDone]);

  const uploadFile = useCallback(async (file: File) => {
    // Client-side validation
    const allowedTypes = ["application/pdf", "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
    if (!allowedTypes.includes(file.type)) {
      setErrorMessage("Please upload a PDF or Word document (.pdf, .doc, .docx)");
      setState("error");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setErrorMessage("File is too large. Maximum size is 10MB.");
      setState("error");
      return;
    }

    setState("uploading");
    setErrorMessage("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiAuthFetch("/api/v1/resumes/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Upload failed");
      }

      const data: UploadResponse = await res.json();
      setUploadResult(data);
      if (autoApply) {
        setState("applying");
        await applyResumeToProfile(data);
        return;
      }
      setState("parsed");
    } catch (err) {
      if (err instanceof ApiUnreachableError) {
        setErrorMessage(
          `Can't reach the backend (${DIRECT_API_URL}). Start the API, then try again.`
        );
      } else {
        setErrorMessage(err instanceof Error ? err.message : "Upload failed");
      }
      setState("error");
    }
  }, [applyResumeToProfile, autoApply]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setState("idle");
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    },
    [uploadFile]
  );

  const handleApplyToProfile = async () => {
    if (!uploadResult) return;
    setState("applying");
    await applyResumeToProfile(uploadResult);
  };

  const reset = () => {
    setState("idle");
    setUploadResult(null);
    setErrorMessage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ── Current résumé on file — show it with a Replace button ────────────────
  if (currentFileName && !showDropzone && state === "idle") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-ink-100 bg-ink-50 p-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-paper-0 border border-ink-100">
            <svg className="h-5 w-5 text-ink-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-ink-900">{currentFileName}</p>
            <p className="text-xs text-ink-500">Résumé on file</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowDropzone(true)}
          className="shrink-0 rounded-full border border-ink-200 px-4 py-1.5 text-sm font-medium text-ink-900 hover:bg-paper-0"
        >
          Replace
        </button>
      </div>
    );
  }

  // ── Idle / Drag drop zone ─────────────────────────────────────────────────
  if (state === "idle" || state === "dragging") {
    return (
      <div
        onDragOver={(e) => { e.preventDefault(); setState("dragging"); }}
        onDragLeave={() => setState("idle")}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all select-none",
          state === "dragging"
            ? "border-accent bg-ink-50"
            : "border-ink-100 hover:border-ink-300 hover:bg-ink-50"
        )}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-ink-50 border border-ink-100 flex items-center justify-center">
            <svg className="w-6 h-6 text-ink-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <p className="font-semibold text-ink-900">
              {state === "dragging" ? "Drop it here" : "Upload your resume"}
            </p>
            <p className="text-sm text-ink-500 mt-1">
              Drag & drop or click to browse · PDF or Word · max 10MB
            </p>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadFile(file);
          }}
        />
      </div>
    );
  }

  // ── Uploading ─────────────────────────────────────────────────────────────
  if (state === "uploading") {
    return (
      <div className="border-2 border-dashed border-ink-100 rounded-2xl p-10 text-center bg-ink-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-3 border-ink-100 border-t-accent rounded-full animate-spin" />
          <p className="font-medium text-accent">Uploading & parsing your resume…</p>
          <p className="text-sm text-ink-900">Aarya is extracting your skills and experience</p>
        </div>
      </div>
    );
  }

  // ── Parsed preview ─────────────────────────────────────────────────────────
  if (state === "parsed" && uploadResult) {
    const p = uploadResult.parsed;
    return (
      <div className="border border-ink-100 rounded-2xl overflow-hidden bg-ink-50">
        <div className="bg-ink-100 px-5 py-3 flex items-center gap-2">
          <svg className="w-5 h-5 text-ink-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-ink-900 font-semibold text-sm">Resume parsed successfully</span>
        </div>

        <div className="p-5 space-y-4">
          {/* Extracted info */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            {p.full_name && <Field label="Name" value={p.full_name} />}
            {p.current_title && <Field label="Current title" value={p.current_title} />}
            {p.current_company && <Field label="Company" value={p.current_company} />}
            {p.years_experience != null && (
              <Field label="Experience" value={`${p.years_experience} years`} />
            )}
            {p.location_city && (
              <Field label="Location" value={[p.location_city, p.location_state].filter(Boolean).join(", ")} />
            )}
          </div>

          {/* Skills */}
          {p.skills.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-ink-500 uppercase tracking-wide mb-2">
                Skills detected ({p.skills.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {p.skills.slice(0, 20).map((skill) => (
                  <span key={skill} className="bg-paper-1 border border-ink-100 text-ink-700 text-xs px-2 py-0.5 rounded-full">
                    {skill}
                  </span>
                ))}
                {p.skills.length > 20 && (
                  <span className="text-xs text-ink-500">+{p.skills.length - 20} more</span>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleApplyToProfile}
              className="flex-1 bg-accent hover:bg-accent-hover text-on-accent font-semibold py-2.5 px-4 rounded-xl text-sm transition-colors"
            >
              Apply to my profile →
            </button>
            <button
              type="button"
              onClick={reset}
              className="px-4 py-2.5 border border-ink-100 text-ink-700 rounded-xl text-sm hover:bg-ink-50 transition-colors"
            >
              Upload different
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Applying ───────────────────────────────────────────────────────────────
  if (state === "applying") {
    return (
      <div className="border border-ink-100 rounded-2xl p-8 text-center bg-ink-50">
        <div className="w-8 h-8 border-2 border-ink-100 border-t-accent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-accent font-medium text-sm">Updating your profile…</p>
      </div>
    );
  }

  // ── Done ──────────────────────────────────────────────────────────────────
  if (state === "done") {
    return (
      <div className="border border-ink-100 rounded-2xl p-6 text-center bg-ink-50">
        <div className="w-10 h-10 rounded-full bg-ink-100 flex items-center justify-center mx-auto mb-3">
          <svg className="w-5 h-5 text-ink-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-ink-900 font-semibold">Profile updated from resume</p>
        <p className="text-ink-900 text-sm mt-1">Aarya now has everything she needs to find your matches.</p>
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  return (
    <div className="border border-destructive rounded-2xl p-5 bg-destructive-bg">
      <p className="text-destructive text-sm font-medium mb-3">{errorMessage}</p>
      <button
        type="button"
        onClick={reset}
        className="text-sm text-destructive hover:text-destructive underline transition-colors"
      >
        Try again
      </button>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-paper-1 rounded-lg px-3 py-2 border border-ink-100">
      <p className="text-xs text-ink-500">{label}</p>
      <p className="text-ink-900 font-medium text-sm truncate">{value}</p>
    </div>
  );
}
