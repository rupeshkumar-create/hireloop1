"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Building2, Briefcase, User } from "@/components/brand/icons";
import { Button, Card, CardBody, CardHeader, Field, Input, Textarea } from "@/components/ui";
import {
  fetchRecruiterProfile,
  updateRecruiterProfile,
  type RecruiterProfile,
} from "@/lib/api/recruiter";

export default function RecruiterSettingsPage() {
  const [profile, setProfile] = useState<RecruiterProfile | null>(null);
  const [title, setTitle] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [focus, setFocus] = useState("");
  const [fromRoles, setFromRoles] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchRecruiterProfile()
      .then((p) => {
        setProfile(p);
        setCompanyName(p.company_name ?? "");
        setTitle(p.title ?? "");
        setFocus(p.hiring_focus ?? "");
        setFromRoles(Boolean(p.profile_from_roles));
      })
      .finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true);
    setSaved(false);
    try {
      const updated = await updateRecruiterProfile({
        recruiter_title: title.trim() || undefined,
        ...(fromRoles
          ? {}
          : {
              company_name: companyName.trim() || undefined,
              hiring_focus: focus.trim() || undefined,
            }),
      });
      setProfile(updated);
      setCompanyName(updated.company_name ?? "");
      setFocus(updated.hiring_focus ?? "");
      setFromRoles(Boolean(updated.profile_from_roles));
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
        <CardBody className="space-y-4">
          {loading ? (
            <p className="text-small text-ink-500">Loading…</p>
          ) : (
            <>
              {fromRoles && (
                <p className="text-small text-ink-500">
                  Company and hiring focus are synced from your active job roles.
                  Edit them on each role, or add a new role.
                </p>
              )}
              <Field
                label={
                  <span className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                    Company name
                  </span>
                }
              >
                <Input
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Acme India Pvt Ltd"
                  readOnly={fromRoles}
                  aria-readonly={fromRoles}
                />
              </Field>
              <Field
                label={
                  <span className="flex items-center gap-2">
                    <User className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                    Your title
                  </span>
                }
              >
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Head of Talent"
                />
              </Field>
              <Field
                label={
                  <span className="flex items-center gap-2">
                    <Briefcase className="h-4 w-4 text-ink-400" strokeWidth={1.5} />
                    Hiring focus
                  </span>
                }
                helper={
                  fromRoles
                    ? "Built from your open roles below."
                    : "Summarize what you hire for, or create a role to sync automatically."
                }
              >
                <Textarea
                  value={focus}
                  onChange={(e) => setFocus(e.target.value)}
                  rows={4}
                  placeholder="e.g. Senior engineers in Bangalore, product leaders remote"
                  readOnly={fromRoles}
                  aria-readonly={fromRoles}
                />
              </Field>
              {profile?.active_roles && profile.active_roles.length > 0 && (
                <div className="space-y-2">
                  <p className="text-micro font-medium text-ink-600">Active roles</p>
                  <ul className="space-y-1.5">
                    {profile.active_roles.map((role) => (
                      <li key={role.id}>
                        <Link
                          href={`/recruiter/roles/${role.id}/intake`}
                          className="text-small text-accent hover:underline"
                        >
                          {role.title}
                          {role.location_city ? ` · ${role.location_city}` : ""}
                          {role.status ? ` (${role.status})` : ""}
                        </Link>
                      </li>
                    ))}
                  </ul>
                  <Link
                    href="/recruiter/roles"
                    className="inline-block text-micro text-ink-500 hover:text-ink-700"
                  >
                    Manage all roles →
                  </Link>
                </div>
              )}
              <Button variant="primary" loading={saving} onClick={() => void save()}>
                Save
              </Button>
              {saved && <p className="text-micro text-ink-500">Saved.</p>}
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
