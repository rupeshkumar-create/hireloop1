"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Brain,
  ExternalLink,
  Linkedin,
  Mail,
  MapPin,
  Phone,
  Zap,
} from "@/components/brand/icons";
import { PublicProfileChat } from "@/components/public-portfolio/PublicProfileChat";
import { PublicPortfolioRecruiterBar } from "@/components/public-portfolio/PublicPortfolioRecruiterBar";
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
              <p className="text-micro text-accent font-medium">
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

  const label = displayLabel(profile);
  const subtitle = roleLine(profile);
  const contactGated = Boolean(profile.contact.requires_registration);
  const location = profile.contact.hidden
    ? null
    : [profile.location_city, profile.location_state].filter(Boolean).join(", ");
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
      <div className="relative max-w-3xl mx-auto px-4 sm:px-6 py-8 sm:py-12 space-y-8">
        <div className="flex items-center justify-between">
          <Link href="/" className="hover:opacity-90 transition-opacity">
            <HireschemaLogo size={28} />
          </Link>
        </div>

        {job && (
          <p className="text-small text-ink-600">
            Open role: <span className="font-medium text-ink-900">{job.title}</span>
            {job.company_name ? ` · ${job.company_name}` : ""}
          </p>
        )}

        <header className="space-y-4">
          <div className="flex items-start gap-4">
            {showPhoto ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={profile.avatar_url!}
                alt=""
                className="h-16 w-16 rounded-lg object-cover border border-ink-100 shrink-0"
              />
            ) : (
              <div className="h-16 w-16 rounded-lg bg-ink-100 text-ink-700 flex items-center justify-center text-h3 font-semibold shrink-0">
                {label.slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 space-y-1">
              <h1 className="text-h2 font-semibold text-ink-900 leading-tight">{label}</h1>
              {subtitle && <p className="text-small text-ink-500">{subtitle}</p>}
              {location && (
                <p className="flex items-center gap-1.5 text-micro text-ink-500">
                  <MapPin className="h-3.5 w-3.5" strokeWidth={1.5} />
                  {location}
                </p>
              )}
            </div>
          </div>

          {profile.looking_for && (
            <p className="text-small text-ink-700">Open to: {profile.looking_for}</p>
          )}

          <PublicPortfolioRecruiterBar profile={profile} />
        </header>

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
                    ? "border-ink-900 text-ink-900"
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
              {profile.summary ? (
                <p className="text-body text-ink-600 leading-relaxed whitespace-pre-wrap">
                  {profile.summary}
                </p>
              ) : (
                <p className="text-small text-ink-500">
                  Ask Aarya below about {label}&apos;s background and fit.
                </p>
              )}

              {profile.skills.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {profile.skills.slice(0, 12).map((skill) => (
                    <span
                      key={skill}
                      className="px-2.5 py-1 text-micro rounded-md bg-ink-50 text-ink-700"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              )}
            </section>
          )}

          {tab === "intelligence" && intel && <IntelligenceSection intel={intel} />}

          {tab === "resume" && (
            <section className="space-y-8">
              {profile.experience.length > 0 && (
                <div>
                  <h2 className="text-h3 font-semibold text-ink-900 mb-4">Experience</h2>
                  <ul className="space-y-4">
                    {profile.experience.map((exp, i) => {
                      const dates = formatDateRange(exp.start_date, exp.end_date);
                      return (
                        <li
                          key={`${exp.title}-${i}`}
                          className="space-y-1 border-b border-ink-100 pb-4 last:border-0"
                        >
                          <p className="text-small font-semibold text-ink-900">
                            {exp.title ?? "Role"}
                          </p>
                          {exp.company && (
                            <p className="text-micro text-ink-500">{exp.company}</p>
                          )}
                          {!exp.company && profile.contact.hidden && (
                            <p className="text-micro text-ink-400 italic">Company confidential</p>
                          )}
                          {dates && <p className="text-micro text-ink-500">{dates}</p>}
                          {exp.description && (
                            <p className="text-small text-ink-600 leading-relaxed pt-1">
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
                  <h2 className="text-h3 font-semibold text-ink-900 mb-4">Education</h2>
                  <ul className="space-y-3">
                    {profile.education.map((edu, i) => {
                      const dates = formatDateRange(edu.start_date, edu.end_date);
                      return (
                        <li key={`${edu.institution}-${i}`}>
                          <p className="text-small font-semibold text-ink-900">
                            {edu.institution ?? "Institution"}
                          </p>
                          <p className="text-micro text-ink-500">
                            {[edu.degree, edu.field_of_study, dates].filter(Boolean).join(" · ")}
                          </p>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {profile.experience.length === 0 && profile.education.length === 0 && (
                <p className="text-small text-ink-500">
                  Detailed experience is available through Aarya — use chat below.
                </p>
              )}
            </section>
          )}

          {tab === "contact" && (
            <section className="space-y-4">
              {profile.contact.hidden ? (
                <>
                  <p className="text-body text-ink-600">
                    Contact details are private. Join as a recruiter to request a warm intro.
                  </p>
                  <Link
                    href={recruiterAuthUrl({ from: `/p/${profile.slug}` })}
                    className="inline-flex text-small font-medium text-ink-900 underline underline-offset-2"
                  >
                    Sign up as a recruiter
                  </Link>
                </>
              ) : contactGated ? (
                <>
                  <p className="text-body text-ink-600">
                    Sign in to view email, phone, and LinkedIn.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Link
                      href={recruiterAuthUrl({ from: `/p/${profile.slug}` })}
                      className="inline-flex text-small font-medium text-ink-900 underline underline-offset-2"
                    >
                      Sign up
                    </Link>
                    <Link
                      href={recruiterAuthUrl({ from: `/p/${profile.slug}`, mode: "signin" })}
                      className="inline-flex text-small font-medium text-ink-600 underline underline-offset-2"
                    >
                      Log in
                    </Link>
                  </div>
                </>
              ) : (
                <ul className="space-y-2.5">
                  {profile.contact.email && (
                    <li>
                      <a
                        href={`mailto:${profile.contact.email}`}
                        className="flex items-center gap-2.5 text-small text-ink-700 hover:text-ink-900"
                      >
                        <Mail className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                        {profile.contact.email}
                      </a>
                    </li>
                  )}
                  {profile.contact.phone && (
                    <li className="flex items-center gap-2.5 text-small text-ink-700">
                      <Phone className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                      {profile.contact.phone}
                    </li>
                  )}
                  {profile.linkedin_url && (
                    <li>
                      <a
                        href={profile.linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2.5 text-small text-ink-700 hover:text-ink-900"
                      >
                        <Linkedin className="h-4 w-4 shrink-0 text-ink-400" strokeWidth={1.5} />
                        LinkedIn
                        <ExternalLink className="h-3 w-3 opacity-60" strokeWidth={1.5} />
                      </a>
                    </li>
                  )}
                </ul>
              )}
            </section>
          )}
        </div>

        <PublicProfileChat
          slug={profile.slug}
          candidateLabel={label}
          chatTargetName={chatTargetName(profile)}
        />
      </div>
    </div>
  );
}
