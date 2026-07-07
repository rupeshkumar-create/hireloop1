"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText } from "@/components/brand/icons";
import { fetchMyProfile, updateMyProfile } from "@/lib/api/profile";
import { Button, Card, CardBody, CardFooter, CardHeader, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-5 w-9 rounded-full transition-colors duration-fast ease-out-soft shrink-0",
        checked ? "bg-accent" : "bg-ink-100",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-paper-1 shadow-1 transition-transform duration-fast",
          checked ? "translate-x-[18px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

export function TailoredResumeSettings() {
  const { toast } = useToast();
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const profile = await fetchMyProfile({ force: true });
      setEnabled(profile.candidate?.tailored_resume_enabled ?? false);
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't load resume settings");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setSaving(true);
    try {
      await updateMyProfile({ tailored_resume_enabled: enabled });
      toast.success(
        enabled
          ? "Tailored resumes enabled — Aarya can generate role-specific CVs"
          : "Tailored resumes turned off",
      );
    } catch (err) {
      toast.error((err as Error).message ?? "Couldn't save setting");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Tailored resumes"
        description="Let Aarya generate a role-specific resume from your profile when you prepare an application."
      />
      <CardBody className="space-y-3 !pt-0">
        {loading ? (
          <p className="text-small text-ink-500">Loading…</p>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <p className="text-small font-medium text-ink-900 inline-flex items-center gap-2">
                  <FileText className="h-4 w-4 text-accent shrink-0" strokeWidth={1.5} />
                  Enable tailored resumes
                </p>
                <p className="text-micro text-ink-500 leading-relaxed">
                  Off by default. When on, Aarya rewrites your CV for each job using your
                  uploaded resume, experience, and profile — without changing employers, dates,
                  titles, or metrics.
                </p>
              </div>
              <Toggle checked={enabled} onChange={setEnabled} disabled={saving} />
            </div>
            {!enabled && (
              <p className="text-micro text-ink-400 border border-ink-100 bg-paper-1 rounded-lg px-3 py-2">
                Cover letters and interview prep still work when this is off. Only the
                tailored resume PDF is skipped.
              </p>
            )}
          </>
        )}
      </CardBody>
      <CardFooter>
        <Button variant="primary" size="sm" loading={saving} disabled={loading} onClick={() => void save()}>
          Save
        </Button>
      </CardFooter>
    </Card>
  );
}
