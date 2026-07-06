"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Briefcase,
  ChevronDown,
  ExternalLink,
  GraduationCap,
  Linkedin,
  Mail,
  MapPin,
  Phone,
  Sparkles,
} from "@/components/brand/icons";
import { PublicProfileChat } from "@/components/public-portfolio/PublicProfileChat";
import { HireschemaLogo } from "@/components/brand/HireschemaLogo";
import { cn } from "@/lib/utils";
import type { PublicProfile } from "@/lib/api/publicProfile";

type TabId = "about" | "resume" | "contact";

function initials(name: string | null | undefined): string {
  const parts = (name ?? "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (!parts.length) return "?";
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("");
}

function formatDateRange(
  start?: string | null,
  end?: string | null,
): string | null {
  const s = start?.trim();
  const e = end?.trim();
  if (s && e) return `${s} — ${e}`;
  if (s) return `${s} — Present`;
  if (e) return e;
  return null;
}

export function PublicPortfolio({ profile }: { profile: PublicProfile }) {
  const [tab, setTab] = useState<TabId>("about");
  const [contactsOpen, setContactsOpen] = useState(false);

  const displayName =
    profile.display_name ?? profile.headline ?? "Candidate";
  const roleLine = [profile.current_title, profile.current_company]
    .filter(Boolean)
    .join(" @ ");
  const location = [profile.location_city, profile.location_state]
    .filter(Boolean)
    .join(", ");
  const hasContact =
    !profile.contact.hidden &&
    (profile.contact.email || profile.contact.phone || profile.linkedin_url);

  const tabs: { id: TabId; label: string }[] = [
    { id: "about", label: "About" },
    { id: "resume", label: "Resume" },
    { id: "contact", label: "Contact" },
  ];

  return (
    <div className="min-h-screen bg-paper-0 text-ink-900">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <div className="flex items-center justify-between mb-6 sm:mb-8">
          <Link href="/" className="hover:opacity-90 transition-opacity">
            <HireschemaLogo size={28} />
          </Link>
          <span className="text-micro uppercase tracking-widest text-ink-500">
            Portfolio
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] gap-6 lg:gap-8">
          {/* ── Sidebar (vCard) ─────────────────────────────────────────── */}
          <aside className="lg:sticky lg:top-8 lg:self-start">
            <div className="border border-ink-100 bg-paper-1 p-6 space-y-5">
              <div className="flex flex-col items-center text-center gap-4">
                {profile.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={profile.avatar_url}
                    alt=""
                    className="h-28 w-28 rounded-full object-cover border-2 border-ink-100"
                  />
                ) : (
                  <div
                    className={cn(
                      "h-28 w-28 rounded-full flex items-center justify-center",
                      "bg-ink-100 text-h1 font-semibold text-ink-900 border-2 border-accent/40",
                    )}
                    aria-hidden
                  >
                    {initials(profile.display_name ?? profile.headline)}
                  </div>
                )}

                <div className="space-y-1">
                  <h1 className="text-h2 font-semibold text-ink-900">{displayName}</h1>
                  {roleLine && (
                    <p className="text-small text-ink-500">{roleLine}</p>
                  )}
                  {profile.looking_for && (
                    <p className="text-micro text-accent pt-1">
                      Open to: {profile.looking_for}
                    </p>
                  )}
                </div>
              </div>

              {hasContact && (
                <div className="border-t border-ink-100 pt-4">
                  <button
                    type="button"
                    onClick={() => setContactsOpen((v) => !v)}
                    className="w-full flex items-center justify-between text-small font-medium text-ink-900 hover:text-accent transition-colors"
                  >
                    Show contacts
                    <ChevronDown
                      className={cn(
                        "h-4 w-4 transition-transform",
                        contactsOpen && "rotate-180",
                      )}
                      strokeWidth={1.75}
                    />
                  </button>

                  {contactsOpen && (
                    <ul className="mt-3 space-y-2.5">
                      {profile.contact.email && (
                        <li>
                          <a
                            href={`mailto:${profile.contact.email}`}
                            className="flex items-center gap-2.5 text-small text-ink-600 hover:text-accent transition-colors"
                          >
                            <Mail className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                            <span className="truncate">{profile.contact.email}</span>
                          </a>
                        </li>
                      )}
                      {profile.contact.phone && (
                        <li className="flex items-center gap-2.5 text-small text-ink-600">
                          <Phone className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                          <span>{profile.contact.phone}</span>
                        </li>
                      )}
                      {location && (
                        <li className="flex items-center gap-2.5 text-small text-ink-600">
                          <MapPin className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                          <span>{location}</span>
                        </li>
                      )}
                      {profile.linkedin_url && (
                        <li>
                          <a
                            href={profile.linkedin_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2.5 text-small text-ink-600 hover:text-accent transition-colors"
                          >
                            <Linkedin className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                            LinkedIn
                            <ExternalLink className="h-3 w-3 opacity-60" strokeWidth={1.5} />
                          </a>
                        </li>
                      )}
                    </ul>
                  )}
                </div>
              )}

              {!hasContact && location && (
                <p className="flex items-center justify-center gap-1.5 text-micro text-ink-500 border-t border-ink-100 pt-4">
                  <MapPin className="h-3.5 w-3.5" strokeWidth={1.5} />
                  {location}
                </p>
              )}

              <div className="border-t border-ink-100 pt-4 space-y-2">
                {typeof profile.years_experience === "number" && profile.years_experience > 0 && (
                  <p className="flex items-center gap-2 text-micro text-ink-500">
                    <Briefcase className="h-3.5 w-3.5" strokeWidth={1.5} />
                    {profile.years_experience}+ years experience
                  </p>
                )}
                <p className="flex items-center gap-2 text-micro text-ink-500">
                  <Sparkles className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
                  Powered by Hireschema
                </p>
              </div>
            </div>
          </aside>

          {/* ── Main content ────────────────────────────────────────────── */}
          <div className="min-w-0">
            <nav
              className="flex gap-1 border-b border-ink-100 mb-6 overflow-x-auto"
              aria-label="Portfolio sections"
            >
              {tabs.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "px-4 py-2.5 text-small font-medium whitespace-nowrap transition-colors",
                    "border-b-2 -mb-px",
                    tab === t.id
                      ? "border-accent text-ink-900"
                      : "border-transparent text-ink-500 hover:text-ink-700",
                  )}
                  aria-current={tab === t.id ? "page" : undefined}
                >
                  {t.label}
                </button>
              ))}
            </nav>

            {tab === "about" && (
              <section className="space-y-6">
                <div>
                  <h2 className="text-h3 font-semibold text-ink-900 mb-3">About me</h2>
                  {profile.summary ? (
                    <p className="text-body text-ink-600 leading-relaxed whitespace-pre-wrap">
                      {profile.summary}
                    </p>
                  ) : (
                    <p className="text-small text-ink-500">
                      {displayName} keeps their public summary on Hireschema — use the chat
                      below to ask Aarya about their background.
                    </p>
                  )}
                </div>

                {profile.skills.length > 0 && (
                  <div>
                    <h3 className="text-small font-semibold text-ink-900 mb-3">Skills</h3>
                    <div className="flex flex-wrap gap-2">
                      {profile.skills.map((skill) => (
                        <span
                          key={skill}
                          className="px-3 py-1.5 text-micro border border-ink-100 bg-paper-1 text-ink-700"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {profile.looking_for && (
                  <div className="border border-ink-100 bg-paper-1 p-5">
                    <h3 className="text-small font-semibold text-ink-900 mb-1">
                      What I&apos;m looking for
                    </h3>
                    <p className="text-body text-ink-600">{profile.looking_for}</p>
                  </div>
                )}
              </section>
            )}

            {tab === "resume" && (
              <section className="space-y-8">
                {profile.experience.length > 0 && (
                  <div>
                    <h2 className="text-h3 font-semibold text-ink-900 mb-4 flex items-center gap-2">
                      <Briefcase className="h-5 w-5 text-accent" strokeWidth={1.5} />
                      Experience
                    </h2>
                    <ul className="space-y-4">
                      {profile.experience.map((exp, i) => {
                        const dates = formatDateRange(exp.start_date, exp.end_date);
                        return (
                          <li
                            key={`${exp.company}-${exp.title}-${i}`}
                            className="border border-ink-100 bg-paper-1 p-5 space-y-2"
                          >
                            <div>
                              <p className="text-small font-semibold text-ink-900">
                                {exp.title ?? "Role"}
                              </p>
                              {exp.company && (
                                <p className="text-micro text-ink-500">{exp.company}</p>
                              )}
                              {dates && (
                                <p className="text-micro text-accent mt-1">{dates}</p>
                              )}
                            </div>
                            {exp.description && (
                              <p className="text-small text-ink-600 leading-relaxed line-clamp-6">
                                {exp.description}
                              </p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                {profile.education.length > 0 && (
                  <div>
                    <h2 className="text-h3 font-semibold text-ink-900 mb-4 flex items-center gap-2">
                      <GraduationCap className="h-5 w-5 text-accent" strokeWidth={1.5} />
                      Education
                    </h2>
                    <ul className="space-y-4">
                      {profile.education.map((edu, i) => {
                        const dates = formatDateRange(edu.start_date, edu.end_date);
                        return (
                          <li
                            key={`${edu.institution}-${edu.degree}-${i}`}
                            className="border border-ink-100 bg-paper-1 p-5"
                          >
                            <p className="text-small font-semibold text-ink-900">
                              {edu.institution ?? "Institution"}
                            </p>
                            <p className="text-micro text-ink-500">
                              {[edu.degree, edu.field_of_study].filter(Boolean).join(" · ")}
                            </p>
                            {dates && (
                              <p className="text-micro text-accent mt-1">{dates}</p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}

                {profile.experience.length === 0 && profile.education.length === 0 && (
                  <p className="text-small text-ink-500">
                    Detailed experience is available through Aarya — tap chat to learn more.
                  </p>
                )}
              </section>
            )}

            {tab === "contact" && (
              <section className="space-y-6">
                <h2 className="text-h3 font-semibold text-ink-900">Get in touch</h2>

                {profile.contact.hidden ? (
                  <div className="border border-ink-100 bg-paper-1 p-6 space-y-3">
                    <p className="text-body text-ink-600">
                      This candidate keeps contact details private on their public portfolio.
                      Chat with Aarya below to learn about their fit, or join Hireschema as a
                      recruiter to request a warm intro.
                    </p>
                    <Link
                      href={`/signup?role=recruiter&from=${encodeURIComponent(`/p/${profile.slug}`)}`}
                      className="inline-flex text-small font-medium text-accent hover:underline"
                    >
                      Sign up as a recruiter →
                    </Link>
                  </div>
                ) : (
                  <ul className="border border-ink-100 bg-paper-1 divide-y divide-ink-100">
                    {profile.contact.email && (
                      <li className="p-4">
                        <a
                          href={`mailto:${profile.contact.email}`}
                          className="flex items-center gap-3 text-body text-ink-700 hover:text-accent transition-colors"
                        >
                          <Mail className="h-5 w-5 text-ink-400" strokeWidth={1.5} />
                          {profile.contact.email}
                        </a>
                      </li>
                    )}
                    {profile.contact.phone && (
                      <li className="p-4 flex items-center gap-3 text-body text-ink-700">
                        <Phone className="h-5 w-5 text-ink-400" strokeWidth={1.5} />
                        {profile.contact.phone}
                      </li>
                    )}
                    {profile.linkedin_url && (
                      <li className="p-4">
                        <a
                          href={profile.linkedin_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-3 text-body text-ink-700 hover:text-accent transition-colors"
                        >
                          <Linkedin className="h-5 w-5 text-ink-400" strokeWidth={1.5} />
                          LinkedIn profile
                        </a>
                      </li>
                    )}
                  </ul>
                )}
              </section>
            )}
          </div>
        </div>
      </div>

      <PublicProfileChat slug={profile.slug} candidateLabel={displayName} />
    </div>
  );
}
