"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Brain,
  Briefcase,
  ChevronDown,
  ExternalLink,
  GraduationCap,
  Linkedin,
  Mail,
  MapPin,
  Phone,
  Sparkles,
  Target,
  Zap,
} from "@/components/brand/icons";
import { PublicProfileChat } from "@/components/public-portfolio/PublicProfileChat";
import { PublicPortfolioRecruiterBar } from "@/components/public-portfolio/PublicPortfolioRecruiterBar";
import { PortfolioIllustration } from "@/components/public-portfolio/PortfolioIllustration";
import { HireschemaLogo } from "@/components/brand/HireschemaLogo";
import { recruiterAuthUrl } from "@/lib/auth/post-auth-redirect";
import { cn } from "@/lib/utils";
import type { PublicIntelligence, PublicProfile } from "@/lib/api/publicProfile";

type TabId = "about" | "intelligence" | "resume" | "contact";

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

function displayLabel(profile: PublicProfile): string {
  if (profile.display_name) return profile.display_name;
  if (profile.headline) return profile.headline;
  if (profile.current_title) return profile.current_title;
  return "Candidate";
}

function chatTargetName(profile: PublicProfile): string {
  const job = profile.job_context;
  if (job?.recruiter_name?.trim()) {
    return job.recruiter_name.trim();
  }
  const label = displayLabel(profile);
  const first = label.trim().split(/\s+/)[0];
  return first || label;
}

function roleLine(profile: PublicProfile): string | null {
  const title = profile.current_title;
  const company = profile.contact.hidden ? null : profile.current_company;
  if (title && company) return `${title} @ ${company}`;
  if (title) return title;
  if (profile.headline) return profile.headline;
  return null;
}

function ScoreBar({ label, value }: { label: string; value?: number | null }) {
  if (value == null || Number.isNaN(value)) return null;
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-micro text-ink-500">
        <span>{label}</span>
        <span className="font-medium text-ink-900">{pct}</span>
      </div>
      <div className="h-1.5 rounded-full bg-ink-100 overflow-hidden">
        <div
          className="h-full rounded-full bg-accent transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function IntelligenceSection({ intel }: { intel: PublicIntelligence }) {
  const dna = intel.career_dna;
  const scores = Object.entries(intel.employability ?? {}).filter(
    ([k, v]) => k.endsWith("_score") && typeof v === "number",
  ) as Array<[string, number]>;

  const hasContent =
    dna?.primary_archetype ||
    intel.prediction?.most_likely_next_role ||
    scores.length > 0 ||
    (intel.achievements?.highlights?.length ?? 0) > 0;

  if (!hasContent) {
    return (
      <p className="text-small text-ink-500">
        Aarya is still building this candidate&apos;s intelligence profile. Use the chat
        below to ask about their background.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {(dna?.primary_archetype || intel.prediction?.most_likely_next_role) && (
        <div className="relative overflow-hidden rounded-xl border border-ink-100 bg-gradient-to-br from-paper-1 via-paper-0 to-accent/5 p-6">
          <div className="absolute -right-8 -top-8 h-32 w-32 rounded-full bg-accent/10 blur-2xl" aria-hidden />
          <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-2 min-w-0">
              <p className="text-micro uppercase tracking-[0.14em] text-accent font-medium">
                Career DNA
              </p>
              {dna?.primary_archetype && (
                <h3 className="text-h2 font-semibold text-ink-900">{dna.primary_archetype}</h3>
              )}
              {dna?.secondary_archetype && (
                <p className="text-small text-ink-500">
                  Secondary: <span className="text-ink-800">{dna.secondary_archetype}</span>
                </p>
              )}
              {dna?.rationale && (
                <p className="text-small text-ink-600 leading-relaxed max-w-prose">{dna.rationale}</p>
              )}
            </div>
            {intel.data_completeness != null && (
              <div className="shrink-0 rounded-lg border border-accent/30 bg-accent/10 px-4 py-3 text-center">
                <p className="text-h2 font-semibold text-ink-900">{intel.data_completeness}%</p>
                <p className="text-micro text-ink-500">Profile depth</p>
              </div>
            )}
          </div>
          {intel.prediction?.most_likely_next_role && (
            <div className="relative mt-4 flex items-start gap-2 rounded-lg bg-paper-0/80 border border-ink-100 p-4">
              <Zap className="h-4 w-4 text-accent shrink-0 mt-0.5" strokeWidth={1.5} />
              <div>
                <p className="text-micro text-ink-500">Likely next move</p>
                <p className="text-small font-medium text-ink-900">
                  {intel.prediction.most_likely_next_role}
                </p>
                {intel.prediction.outcome_3_year && (
                  <p className="text-micro text-ink-500 mt-1">
                    3-year outlook: {intel.prediction.outcome_3_year}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {scores.length > 0 && (
        <div className="rounded-xl border border-ink-100 bg-paper-1 p-5 space-y-4">
          <h3 className="text-small font-semibold text-ink-900 flex items-center gap-2">
            <Brain className="h-4 w-4 text-accent" strokeWidth={1.5} />
            Employability signals
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {scores.map(([key, val]) => (
              <ScoreBar
                key={key}
                label={key.replace(/_score$/, "").replace(/_/g, " ")}
                value={val}
              />
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {(intel.market?.in_demand_skills?.length ?? 0) > 0 && (
          <div className="rounded-xl border border-ink-100 bg-paper-1 p-5 space-y-3">
            <h3 className="text-small font-semibold text-ink-900">In-demand skills</h3>
            <div className="flex flex-wrap gap-2">
              {intel.market!.in_demand_skills!.map((s) => (
                <span key={s} className="px-2.5 py-1 text-micro rounded-md bg-accent/10 text-ink-800 border border-accent/20">
                  {s}
                </span>
              ))}
            </div>
            {intel.market?.grounded && (
              <p className="text-micro text-ink-500">Grounded in live market data</p>
            )}
          </div>
        )}

        {(intel.skills?.future_skills?.length ?? 0) > 0 && (
          <div className="rounded-xl border border-ink-100 bg-paper-1 p-5 space-y-3">
            <h3 className="text-small font-semibold text-ink-900">Skills to build next</h3>
            <div className="flex flex-wrap gap-2">
              {intel.skills!.future_skills!.map((s) => (
                <span key={s} className="px-2.5 py-1 text-micro rounded-md border border-ink-100 bg-paper-0 text-ink-700">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {(intel.achievements?.highlights?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-ink-100 bg-paper-1 p-5 space-y-3">
          <h3 className="text-small font-semibold text-ink-900">Impact highlights</h3>
          <ul className="space-y-2">
            {intel.achievements!.highlights!.map((h) => (
              <li key={h} className="flex gap-2 text-small text-ink-600 leading-relaxed">
                <span className="text-accent shrink-0">▸</span>
                <span>{h}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {intel.leadership?.leadership_stage && (
          <InfoTile label="Leadership stage" value={intel.leadership.leadership_stage} />
        )}
        {intel.preferences?.work_mode && (
          <InfoTile label="Work mode" value={intel.preferences.work_mode} />
        )}
        {intel.mobility?.relocation_openness && (
          <InfoTile label="Mobility" value={intel.mobility.relocation_openness} />
        )}
        {intel.industry?.transferability_score != null && (
          <InfoTile
            label="Industry transferability"
            value={`${intel.industry.transferability_score}/100`}
          />
        )}
        {intel.learning?.learning_velocity != null && (
          <InfoTile
            label="Learning velocity"
            value={`${intel.learning.learning_velocity} skills/yr`}
          />
        )}
        {intel.experience_vector?.leadership_years != null && (
          <InfoTile
            label="Leadership experience"
            value={`${intel.experience_vector.leadership_years}+ yrs`}
          />
        )}
      </div>

      {(intel.learning?.certifications?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-ink-100 bg-paper-1 p-5">
          <h3 className="text-small font-semibold text-ink-900 mb-2">Certifications</h3>
          <p className="text-small text-ink-600">{intel.learning!.certifications!.join(" · ")}</p>
        </div>
      )}
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-100 bg-paper-1 p-4">
      <p className="text-micro text-ink-500">{label}</p>
      <p className="text-small font-medium text-ink-900 mt-1">{value}</p>
    </div>
  );
}

export function PublicPortfolio({ profile }: { profile: PublicProfile }) {
  const [tab, setTab] = useState<TabId>("about");
  const [contactsOpen, setContactsOpen] = useState(false);

  const label = displayLabel(profile);
  const subtitle = roleLine(profile);
  const contactGated = Boolean(profile.contact.requires_registration);
  const location = profile.contact.hidden
    ? null
    : [profile.location_city, profile.location_state].filter(Boolean).join(", ");
  const hasContact =
    !profile.contact.hidden &&
    !contactGated &&
    (profile.contact.email || profile.contact.phone || profile.linkedin_url);
  const showPhoto = Boolean(profile.avatar_url && !profile.contact.hidden && !contactGated);
  const intel = profile.intelligence;
  const job = profile.job_context;

  const tabs: { id: TabId; label: string }[] = [
    { id: "about", label: "About" },
    ...(intel ? [{ id: "intelligence" as const, label: "Intelligence" }] : []),
    { id: "resume", label: "Resume" },
    { id: "contact", label: "Contact" },
  ];

  return (
    <div className="min-h-screen bg-paper-0 text-ink-900">
      <div className="pointer-events-none fixed inset-0 opacity-[0.4]" aria-hidden>
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(185,248,76,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(185,248,76,0.04) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
            maskImage: "radial-gradient(ellipse 70% 50% at 50% 0%, black, transparent)",
          }}
        />
      </div>

      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <div className="flex items-center justify-between mb-6 sm:mb-8">
          <Link href="/" className="hover:opacity-90 transition-opacity">
            <HireschemaLogo size={28} />
          </Link>
          <span className="text-micro uppercase tracking-widest text-ink-500">Portfolio</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)] gap-6 lg:gap-8">
          <PublicPortfolioRecruiterBar profile={profile} />
          {job && (
            <div className="lg:col-span-2 rounded-xl border border-accent/30 bg-accent/5 px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="min-w-0">
                <p className="text-micro uppercase tracking-widest text-accent font-medium">
                  Open role
                </p>
                <p className="text-body font-semibold text-ink-900 truncate">{job.title}</p>
                {job.company_name && (
                  <p className="text-small text-ink-600">{job.company_name}</p>
                )}
              </div>
              {job.recruiter_name && (
                <p className="text-small text-ink-600 shrink-0">
                  Recruiter: <span className="font-medium text-ink-900">{job.recruiter_name}</span>
                </p>
              )}
            </div>
          )}
          <aside className="lg:sticky lg:top-8 lg:self-start">
            <div className="rounded-xl border border-ink-100 bg-paper-1/90 backdrop-blur-sm p-6 space-y-5 shadow-1">
              <div className="flex flex-col items-center text-center gap-4">
                {showPhoto ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={profile.avatar_url!}
                    alt=""
                    className="h-32 w-32 rounded-2xl object-cover border-2 border-accent/30 shadow-2"
                  />
                ) : (
                  <PortfolioIllustration slug={profile.slug} size="lg" />
                )}

                <div className="space-y-2">
                  <h1 className="text-h2 font-semibold text-ink-900 leading-tight">{label}</h1>
                  {subtitle && <p className="text-small text-ink-500">{subtitle}</p>}
                  {profile.looking_for && (
                    <p className="inline-flex items-center gap-1.5 text-micro text-accent font-medium pt-1">
                      <Target className="h-3.5 w-3.5" strokeWidth={1.5} />
                      Open to: {profile.looking_for}
                    </p>
                  )}
                </div>
              </div>

              {intel?.career_dna?.primary_archetype && (
                <div className="rounded-lg border border-accent/25 bg-accent/5 px-3 py-2.5 text-center">
                  <p className="text-micro text-ink-500">Archetype</p>
                  <p className="text-small font-semibold text-ink-900">
                    {intel.career_dna.primary_archetype}
                  </p>
                </div>
              )}

              {profile.contact.hidden && (
                <p className="text-micro text-ink-500 text-center px-2">
                  Contact details are private — employer names are hidden on this portfolio.
                </p>
              )}

              {contactGated && !profile.contact.hidden && (
                <p className="text-micro text-ink-500 text-center px-2">
                  Sign in to Hireschema to view email, phone, and LinkedIn.
                </p>
              )}

              {hasContact && (
                <div className="border-t border-ink-100 pt-4">
                  <button
                    type="button"
                    onClick={() => setContactsOpen((v) => !v)}
                    className="w-full flex items-center justify-between text-small font-medium text-ink-900 hover:text-accent transition-colors"
                  >
                    Show contacts
                    <ChevronDown
                      className={cn("h-4 w-4 transition-transform", contactsOpen && "rotate-180")}
                      strokeWidth={1.75}
                    />
                  </button>
                  {contactsOpen && (
                    <ul className="mt-3 space-y-2.5">
                      {profile.contact.email && (
                        <li>
                          <a
                            href={`mailto:${profile.contact.email}`}
                            className="flex items-center gap-2.5 text-small text-ink-600 hover:text-accent"
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
                            className="flex items-center gap-2.5 text-small text-ink-600 hover:text-accent"
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

              <div className="border-t border-ink-100 pt-4 space-y-2">
                {typeof profile.years_experience === "number" && profile.years_experience > 0 && (
                  <p className="flex items-center gap-2 text-micro text-ink-500">
                    <Briefcase className="h-3.5 w-3.5" strokeWidth={1.5} />
                    {profile.years_experience}+ years experience
                  </p>
                )}
                {profile.market && (
                  <p className="text-micro text-ink-500">Market: {profile.market}</p>
                )}
                <p className="flex items-center gap-2 text-micro text-ink-500">
                  <Sparkles className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
                  Powered by Hireschema
                </p>
              </div>
            </div>
          </aside>

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
                    "px-4 py-2.5 text-small font-medium whitespace-nowrap transition-colors border-b-2 -mb-px",
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
                <div className="rounded-xl border border-ink-100 bg-paper-1 p-6">
                  <h2 className="text-h3 font-semibold text-ink-900 mb-3">About</h2>
                  {profile.summary ? (
                    <p className="text-body text-ink-600 leading-relaxed whitespace-pre-wrap">
                      {profile.summary}
                    </p>
                  ) : (
                    <p className="text-small text-ink-500">
                      {label} keeps their public summary on Hireschema — use the chat below to
                      ask Aarya about their background and fit.
                    </p>
                  )}
                </div>

                {profile.skills.length > 0 && (
                  <div className="rounded-xl border border-ink-100 bg-paper-1 p-6">
                    <h3 className="text-small font-semibold text-ink-900 mb-3">Core skills</h3>
                    <div className="flex flex-wrap gap-2">
                      {profile.skills.map((skill) => (
                        <span
                          key={skill}
                          className="px-3 py-1.5 text-micro rounded-md border border-ink-100 bg-paper-0 text-ink-700"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {intel?.skills?.hard_skills && intel.skills.hard_skills.length > 0 && (
                  <div className="rounded-xl border border-ink-100 bg-paper-1 p-6">
                    <h3 className="text-small font-semibold text-ink-900 mb-3">
                      Verified skill depth (Aarya)
                    </h3>
                    <ul className="grid gap-2 sm:grid-cols-2">
                      {intel.skills.hard_skills.map((row) => (
                        <li
                          key={row.skill}
                          className="flex items-center justify-between rounded-md border border-ink-100 bg-paper-0 px-3 py-2 text-small"
                        >
                          <span className="text-ink-800">{row.skill}</span>
                          <span className="text-micro text-ink-500">
                            {[row.proficiency, row.years != null ? `${row.years}y` : null]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {profile.looking_for && (
                  <div className="rounded-xl border border-accent/20 bg-accent/5 p-5">
                    <h3 className="text-small font-semibold text-ink-900 mb-1">Looking for</h3>
                    <p className="text-body text-ink-700">{profile.looking_for}</p>
                  </div>
                )}
              </section>
            )}

            {tab === "intelligence" && intel && <IntelligenceSection intel={intel} />}

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
                            key={`${exp.title}-${i}`}
                            className="rounded-xl border border-ink-100 bg-paper-1 p-5 space-y-2"
                          >
                            <div>
                              <p className="text-small font-semibold text-ink-900">
                                {exp.title ?? "Role"}
                              </p>
                              {exp.company && (
                                <p className="text-micro text-ink-500">{exp.company}</p>
                              )}
                              {!exp.company && profile.contact.hidden && (
                                <p className="text-micro text-ink-400 italic">Company confidential</p>
                              )}
                              {dates && (
                                <p className="text-micro text-accent mt-1">{dates}</p>
                              )}
                            </div>
                            {exp.description && (
                              <p className="text-small text-ink-600 leading-relaxed">{exp.description}</p>
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
                            key={`${edu.institution}-${i}`}
                            className="rounded-xl border border-ink-100 bg-paper-1 p-5"
                          >
                            <p className="text-small font-semibold text-ink-900">
                              {edu.institution ?? "Institution"}
                            </p>
                            <p className="text-micro text-ink-500">
                              {[edu.degree, edu.field_of_study].filter(Boolean).join(" · ")}
                            </p>
                            {dates && <p className="text-micro text-accent mt-1">{dates}</p>}
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
                  <div className="rounded-xl border border-ink-100 bg-paper-1 p-6 space-y-3">
                    <p className="text-body text-ink-600">
                      This candidate keeps contact details private. Employer names are also hidden.
                      Chat with Aarya below to learn about their fit, or join Hireschema as a
                      recruiter to request a warm intro.
                    </p>
                    <Link
                      href={recruiterAuthUrl({ from: `/p/${profile.slug}` })}
                      className="inline-flex text-small font-medium text-accent hover:underline"
                    >
                      Sign up as a recruiter →
                    </Link>
                  </div>
                ) : contactGated ? (
                  <div className="rounded-xl border border-ink-100 bg-paper-1 p-6 space-y-3">
                    <p className="text-body text-ink-600">
                      Email, phone, and LinkedIn are only available to registered Hireschema users.
                      Sign up or log in to connect with this candidate through the platform.
                    </p>
                    <div className="flex flex-wrap gap-3">
                      <Link
                        href={recruiterAuthUrl({ from: `/p/${profile.slug}` })}
                        className="inline-flex text-small font-medium text-accent hover:underline"
                      >
                        Sign up →
                      </Link>
                      <Link
                        href={recruiterAuthUrl({ from: `/p/${profile.slug}`, mode: "signin" })}
                        className="inline-flex text-small font-medium text-ink-700 hover:underline"
                      >
                        Log in
                      </Link>
                    </div>
                  </div>
                ) : (
                  <ul className="rounded-xl border border-ink-100 bg-paper-1 divide-y divide-ink-100 overflow-hidden">
                    {profile.contact.email && (
                      <li className="p-4">
                        <a
                          href={`mailto:${profile.contact.email}`}
                          className="flex items-center gap-3 text-body text-ink-700 hover:text-accent"
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
                          className="flex items-center gap-3 text-body text-ink-700 hover:text-accent"
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

      <PublicProfileChat
        slug={profile.slug}
        candidateLabel={label}
        chatTargetName={chatTargetName(profile)}
      />
    </div>
  );
}
