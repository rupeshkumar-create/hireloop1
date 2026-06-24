"use client";

import { useEffect, useState } from "react";
import { Button, Card, CardBody, CardHeader } from "@/components/ui";
import {
  fetchRecruiterProfile,
  updateRecruiterProfile,
} from "@/lib/api/recruiter";

export default function RecruiterSettingsPage() {
  const [companyName, setCompanyName] = useState("");
  const [title, setTitle] = useState("");
  const [focus, setFocus] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchRecruiterProfile()
      .then((p) => {
        setCompanyName(p.company_name ?? "");
        setTitle(p.title ?? "");
        setFocus(p.hiring_focus ?? "");
      })
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      await updateRecruiterProfile({
        company_name: companyName.trim() || undefined,
        recruiter_title: title.trim() || undefined,
        hiring_focus: focus.trim() || undefined,
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto px-6 py-8 space-y-4">
      <h1 className="text-h2 font-semibold text-ink-900">Recruiter settings</h1>
      <Card>
        <CardHeader title="Company & profile" />
        <CardBody className="space-y-3">
          {loading ? (
            <p className="text-small text-ink-500">Loading…</p>
          ) : (
            <>
              <input
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Company name"
                className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body"
              />
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Your title"
                className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body"
              />
              <textarea
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                rows={3}
                placeholder="Hiring focus"
                className="w-full rounded-lg border border-ink-200 px-3 py-2 text-body resize-none"
              />
              <Button variant="primary" loading={saving} onClick={() => void save()}>
                Save
              </Button>
              {saved && (
                <p className="text-micro text-ink-500">Saved.</p>
              )}
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
