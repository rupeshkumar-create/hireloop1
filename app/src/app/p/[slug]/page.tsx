"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Briefcase, FileText, Mail, MapPin, Phone } from "@/components/brand/icons";
import { getApiBaseUrl } from "@/lib/api/base-url";
import { Button, Card, CardBody } from "@/components/ui";

type PublicProfile = {
  slug: string;
  display_name: string | null;
  headline: string | null;
  summary: string | null;
  current_title: string | null;
  current_company: string | null;
  years_experience: number | null;
  location_city: string | null;
  location_state: string | null;
  skills: string[];
  looking_for: string | null;
  linkedin_url: string | null;
  experience: Array<{
    title?: string | null;
    company?: string | null;
    description?: string | null;
  }>;
  education: Array<{
    institution?: string | null;
    degree?: string | null;
  }>;
  career_path_resumes: Array<{
    id: string;
    path_title: string;
    download_path: string;
  }>;
  contact: {
    email: string | null;
    phone: string | null;
    hidden: boolean;
  };
};

export default function PublicProfilePage() {
  const params = useParams();
  const slug = typeof params.slug === "string" ? params.slug : "";
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    void fetch(`${getApiBaseUrl()}/api/v1/public/profiles/${encodeURIComponent(slug)}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            (body as { detail?: string }).detail ?? "Profile not found"
          );
        }
        return res.json() as Promise<PublicProfile>;
      })
      .then(setProfile)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen bg-paper-0 flex items-center justify-center text-ink-500 text-small">
        Loading profile…
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen bg-paper-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-body text-ink-700">{error ?? "Profile unavailable"}</p>
        <Link href="/" className="text-small text-accent hover:underline">
          Go to Hireloop
        </Link>
      </div>
    );
  }

  const location = [profile.location_city, profile.location_state].filter(Boolean).join(", ");

  return (
    <div className="min-h-screen bg-paper-0">
      <header className="border-b border-ink-100 bg-paper-1">
        <div className="max-w-2xl mx-auto px-5 py-4 flex items-center justify-between">
          <Link href="/" className="text-small font-semibold text-ink-900">
            Hireloop
          </Link>
          <span className="text-micro text-ink-500">Public profile</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-8 space-y-6">
        <div className="space-y-2">
          <h1 className="text-h1 font-semibold text-ink-900">
            {profile.display_name ?? profile.headline ?? "Candidate profile"}
          </h1>
          {profile.display_name && profile.headline && (
            <p className="text-body text-ink-600">{profile.headline}</p>
          )}
          <div className="flex flex-wrap gap-3 text-micro text-ink-500">
            {profile.current_title && (
              <span className="inline-flex items-center gap-1">
                <Briefcase className="h-3.5 w-3.5" strokeWidth={1.5} />
                {profile.current_title}
                {profile.current_company ? ` @ ${profile.current_company}` : ""}
              </span>
            )}
            {location && (
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" strokeWidth={1.5} />
                {location}
              </span>
            )}
          </div>
        </div>

        {profile.summary && (
          <Card>
            <CardBody>
              <p className="text-small text-ink-700 leading-relaxed whitespace-pre-wrap">
                {profile.summary}
              </p>
            </CardBody>
          </Card>
        )}

        {!profile.contact.hidden && (profile.contact.email || profile.contact.phone) && (
          <Card>
            <CardBody className="space-y-2">
              <p className="text-small font-medium text-ink-900">Contact</p>
              {profile.contact.email && (
                <a
                  href={`mailto:${profile.contact.email}`}
                  className="flex items-center gap-2 text-small text-accent hover:underline"
                >
                  <Mail className="h-4 w-4" strokeWidth={1.5} />
                  {profile.contact.email}
                </a>
              )}
              {profile.contact.phone && (
                <p className="flex items-center gap-2 text-small text-ink-700">
                  <Phone className="h-4 w-4" strokeWidth={1.5} />
                  {profile.contact.phone}
                </p>
              )}
            </CardBody>
          </Card>
        )}

        {profile.skills.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-h3 font-semibold text-ink-900">Skills</h2>
            <div className="flex flex-wrap gap-1.5">
              {profile.skills.map((s) => (
                <span
                  key={s}
                  className="rounded-full border border-ink-100 bg-paper-1 px-2.5 py-1 text-micro text-ink-700"
                >
                  {s}
                </span>
              ))}
            </div>
          </section>
        )}

        {profile.experience.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-h3 font-semibold text-ink-900">Experience</h2>
            {profile.experience.map((exp, i) => (
              <Card key={`${exp.company}-${exp.title}-${i}`}>
                <CardBody className="space-y-1">
                  <p className="text-small font-medium text-ink-900">
                    {exp.title ?? "Role"}
                    {exp.company ? ` · ${exp.company}` : ""}
                  </p>
                  {exp.description && (
                    <p className="text-micro text-ink-600 line-clamp-4">{exp.description}</p>
                  )}
                </CardBody>
              </Card>
            ))}
          </section>
        )}

        {profile.career_path_resumes.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-h3 font-semibold text-ink-900">Resumes by career path</h2>
            {profile.career_path_resumes.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-ink-100 bg-paper-1 px-4 py-3"
              >
                <span className="text-small text-ink-800">{r.path_title}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  leftIcon={<FileText className="h-3.5 w-3.5" />}
                  onClick={() =>
                    window.open(
                      `${getApiBaseUrl()}/api/v1/public/profiles/${slug}/resumes/${r.id}/download`,
                      "_blank"
                    )
                  }
                >
                  View resume
                </Button>
              </div>
            ))}
          </section>
        )}

        <p className="text-micro text-ink-500 text-center pt-4">
          Interested?{" "}
          <Link href="/signup" className="text-accent hover:underline">
            Join Hireloop
          </Link>{" "}
          to connect with this candidate.
        </p>
      </main>
    </div>
  );
}
