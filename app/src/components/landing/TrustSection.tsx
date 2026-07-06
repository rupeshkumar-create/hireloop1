"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, MessageSquare, Search, Send, ShieldCheck, Zap } from "@/components/brand/icons";
import { LANDING_AGENTS, type LandingAudience } from "@/components/landing/landing-audience";
import { SectionHeader } from "@/components/landing/SectionHeader";
import { Reveal, RevealStagger, StaggerItem } from "@/components/ui/motion";

const TRUST_COPY: Record<
  LandingAudience,
  { action: string; data: string }
> = {
  candidate: {
    action:
      'Aarya logs every search, score, and outreach. "Aarya performed 7 actions on your profile" — always visible.',
    data: "Your CV is shared only with your consent. DPDP-compliant. No spam, no selling your data.",
  },
  recruiter: {
    action:
      'Nitya logs every search, shortlist, and intro. "Nitya performed 5 actions on this role" — always visible.',
    data: "Candidate profiles are shared only with their consent. No cold outreach, no spam.",
  },
};

type TrustSectionProps = {
  audience: LandingAudience;
};

export function TrustSection({ audience }: TrustSectionProps) {
  const agent = LANDING_AGENTS[audience];
  const copy = TRUST_COPY[audience];

  const points = [
    { Icon: Zap, title: "See every action", body: copy.action },
    { Icon: ShieldCheck, title: "Consent-first", body: copy.data },
  ] as const;

  return (
    <section id="trust" className="scroll-mt-20">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="grid gap-12 md:grid-cols-2 md:items-center">
          <SectionHeader
            label={`Trust ${agent.name}`}
            title="No black box. No spam."
            description={`${agent.name} works for you — and you see everything it does.`}
          />

          <RevealStagger key={audience} className="space-y-4">
            {points.map(({ Icon, title, body }) => (
              <StaggerItem key={title}>
                <motion.div
                  className="flex gap-4 rounded-xl border border-ink-100 bg-paper-1 p-5"
                  whileHover={{ x: 4 }}
                  transition={{ type: "spring", stiffness: 400, damping: 28 }}
                >
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10">
                    <Icon className="h-5 w-5 text-accent" strokeWidth={1.5} />
                  </span>
                  <div className="space-y-1">
                    <h3 className="text-h3 text-ink-900">{title}</h3>
                    <p className="text-small leading-relaxed text-ink-600">{body}</p>
                  </div>
                </motion.div>
              </StaggerItem>
            ))}
          </RevealStagger>
        </div>
      </div>
    </section>
  );
}

/** Shown when audience is candidate — cross-sell Nitya for recruiters. */
export function RecruitersSection() {
  const cards = [
    { Icon: Search, title: "Describe the role", body: "Plain words — Nitya builds the brief." },
    { Icon: Zap, title: "Pre-scored matches", body: "Nitya ranks candidates, not résumé piles." },
    { Icon: Send, title: "Warm intros", body: "Candidates who opted in — not cold DMs." },
    { Icon: ShieldCheck, title: "Consent-first", body: "Nitya shares profiles only with permission." },
  ] as const;

  return (
    <section id="recruiters" className="scroll-mt-20 border-t border-ink-100 bg-paper-1">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="grid gap-12 md:grid-cols-2 md:items-center">
          <Reveal>
            <p className="text-micro font-semibold uppercase tracking-[0.14em] text-accent">
              For recruiters · Nitya
            </p>
            <h2 className="mt-3 text-h1 text-ink-900 md:text-[32px]">Hiring? Meet Nitya.</h2>
            <p className="mt-4 text-body leading-relaxed text-ink-600">
              Nitya is the recruiter agent — separate from Aarya. Describe the role in plain
              words and Nitya surfaces pre-scored, genuinely-interested candidates.
            </p>
            <Link
              href="/signup?role=recruiter"
              className="group mt-6 inline-flex items-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-body font-medium text-on-accent transition-colors hover:bg-accent-hover"
            >
              Talk to Nitya
              <Send
                className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
                strokeWidth={1.5}
              />
            </Link>
          </Reveal>

          <RevealStagger className="grid gap-4 sm:grid-cols-2">
            {cards.map(({ Icon, title, body }) => (
              <StaggerItem key={title}>
                <motion.div
                  className="space-y-2 rounded-xl border border-ink-100 bg-paper-0 p-5"
                  whileHover={{ y: -3 }}
                  transition={{ type: "spring", stiffness: 400, damping: 28 }}
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                    <Icon className="h-4 w-4" strokeWidth={1.5} />
                  </span>
                  <h3 className="text-h3 text-ink-900">{title}</h3>
                  <p className="text-small leading-relaxed text-ink-600">{body}</p>
                </motion.div>
              </StaggerItem>
            ))}
          </RevealStagger>
        </div>
      </div>
    </section>
  );
}

/** Shown when audience is recruiter — cross-sell Aarya for candidates. */
export function CandidatesCrossSell({ onSwitch }: { onSwitch: () => void }) {
  const cards = [
    { Icon: MessageSquare, title: "Tell Aarya your goals", body: "Role, location, pay — in plain words." },
    { Icon: Search, title: "Aarya finds live roles", body: "Scored for fit in your market." },
    { Icon: Send, title: "Warm intros", body: "Aarya requests intros — not cold applies." },
    { Icon: ShieldCheck, title: "Your data stays yours", body: "Shared only with your consent." },
  ] as const;

  return (
    <section id="candidates" className="scroll-mt-20 border-t border-ink-100 bg-paper-1">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="grid gap-12 md:grid-cols-2 md:items-center">
          <Reveal>
            <p className="text-micro font-semibold uppercase tracking-[0.14em] text-accent">
              For job seekers · Aarya
            </p>
            <h2 className="mt-3 text-h1 text-ink-900 md:text-[32px]">Job hunting? Meet Aarya.</h2>
            <p className="mt-4 text-body leading-relaxed text-ink-600">
              Aarya is the candidate agent — separate from Nitya. It finds live roles in your
              region, scores your fit, and gets you warm intros in one chat.
            </p>
            <button
              type="button"
              onClick={onSwitch}
              className="group mt-6 inline-flex items-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-body font-medium text-on-accent transition-colors hover:bg-accent-hover"
            >
              Switch to Aarya
              <ArrowRight
                className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
                strokeWidth={1.5}
              />
            </button>
          </Reveal>

          <RevealStagger className="grid gap-4 sm:grid-cols-2">
            {cards.map(({ Icon, title, body }) => (
              <StaggerItem key={title}>
                <motion.div
                  className="space-y-2 rounded-xl border border-ink-100 bg-paper-0 p-5"
                  whileHover={{ y: -3 }}
                  transition={{ type: "spring", stiffness: 400, damping: 28 }}
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                    <Icon className="h-4 w-4" strokeWidth={1.5} />
                  </span>
                  <h3 className="text-h3 text-ink-900">{title}</h3>
                  <p className="text-small leading-relaxed text-ink-600">{body}</p>
                </motion.div>
              </StaggerItem>
            ))}
          </RevealStagger>
        </div>
      </div>
    </section>
  );
}

const CTA_COPY: Record<
  LandingAudience,
  { title: string; sub: string; ctaLabel: string; ctaHref: string }
> = {
  candidate: {
    title: "Your next role is one chat with Aarya away.",
    sub: "Join from anywhere. Aarya adapts to your market, currency, and city — then gets to work.",
    ctaLabel: "Talk to Aarya — free",
    ctaHref: "/signup",
  },
  recruiter: {
    title: "Your next hire is one chat with Nitya away.",
    sub: "Describe the role. Nitya surfaces pre-scored, opted-in candidates — then warms up the intro.",
    ctaLabel: "Talk to Nitya — free",
    ctaHref: "/signup?role=recruiter",
  },
};

type FinalCtaSectionProps = {
  audience: LandingAudience;
};

export function FinalCtaSection({ audience }: FinalCtaSectionProps) {
  const copy = CTA_COPY[audience];

  return (
    <section className="relative overflow-hidden border-t border-ink-100 bg-ink-900">
      <motion.div
        className="pointer-events-none absolute inset-0 opacity-30"
        aria-hidden
        animate={{ backgroundPosition: ["0% 0%", "100% 100%"] }}
        transition={{ duration: 18, repeat: Infinity, repeatType: "reverse", ease: "linear" }}
        style={{
          backgroundImage:
            "radial-gradient(circle at 20% 50%, rgba(185,248,76,0.15), transparent 50%), radial-gradient(circle at 80% 50%, rgba(185,248,76,0.08), transparent 40%)",
          backgroundSize: "200% 200%",
        }}
      />

      <div className="relative mx-auto max-w-page px-6 py-20 text-center">
        <Reveal key={audience}>
          <h2 className="text-h1 text-paper-0 md:text-[32px]">{copy.title}</h2>
          <p className="mx-auto mt-4 max-w-md text-body text-ink-500">{copy.sub}</p>
          <div className="mt-8 flex flex-col items-center gap-3">
            <Link
              href={copy.ctaHref}
              className="group inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-8 py-3.5 text-body font-medium text-on-accent transition-transform hover:scale-[1.02] hover:bg-accent-hover"
            >
              {copy.ctaLabel}
              <ArrowRight
                className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
                strokeWidth={1.5}
              />
            </Link>
            <span className="text-micro text-ink-400">Free · No credit card</span>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function LandingFooter() {
  return (
    <footer className="border-t border-ink-100">
      <div className="mx-auto flex max-w-page flex-col items-center justify-between gap-4 px-6 py-8 text-micro text-ink-400 sm:flex-row">
        <span>© {new Date().getFullYear()} Hireschema</span>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <a href="#process" className="transition-colors hover:text-ink-700">
            How it works
          </a>
          <a href="#features" className="transition-colors hover:text-ink-700">
            Features
          </a>
          <Link href="/login" className="transition-colors hover:text-ink-700">
            Log in
          </Link>
          <Link href="/signup" className="transition-colors hover:text-ink-700">
            Sign up
          </Link>
        </div>
      </div>
    </footer>
  );
}
