"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Search, Send, ShieldCheck, Zap } from "@/components/brand/icons";
import { LandingCta } from "@/components/landing/LandingCta";
import { Reveal, RevealStagger, StaggerItem } from "@/components/ui/motion";
import { SectionHeader } from "@/components/landing/SectionHeader";

export function TrustSection() {
  const points = [
    {
      Icon: Zap,
      title: "See every action",
      body: "Aarya logs every search, score, and outreach. \"Performed 7 actions on your profile\" — always visible.",
    },
    {
      Icon: ShieldCheck,
      title: "Your data stays yours",
      body: "Profiles shared only with your consent. DPDP-compliant. No spam, no selling your CV.",
    },
  ] as const;

  return (
    <section id="trust" className="scroll-mt-20">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="grid gap-12 md:grid-cols-2 md:items-center">
          <SectionHeader
            label="Trust"
            title="No black box. No spam."
            description="You control what gets shared and when. Every agent action is auditable."
          />

          <RevealStagger className="space-y-4">
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

export function RecruitersSection() {
  const cards = [
    { Icon: Search, title: "Describe the role", body: "Plain words — Nitya builds the brief." },
    { Icon: Zap, title: "Pre-scored matches", body: "Ranked candidates, not a résumé pile." },
    { Icon: Send, title: "Warm intros", body: "Candidates who opted in — not cold DMs." },
    { Icon: ShieldCheck, title: "Consent-first", body: "Profiles shared only with permission." },
  ] as const;

  return (
    <section id="recruiters" className="scroll-mt-20 border-t border-ink-100 bg-paper-1">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="grid gap-12 md:grid-cols-2 md:items-center">
          <Reveal>
            <p className="text-micro font-semibold uppercase tracking-[0.14em] text-accent">
              For recruiters
            </p>
            <h2 className="mt-3 text-h1 text-ink-900 md:text-[32px]">Hiring? Meet Nitya.</h2>
            <p className="mt-4 text-body leading-relaxed text-ink-600">
              Describe the role in plain words. Nitya surfaces pre-scored,
              genuinely-interested candidates and warms up the intro — so you skip
              cold sourcing and start real conversations.
            </p>
            <Link
              href="/signup?role=recruiter"
              className="group mt-6 inline-flex items-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-body font-medium text-on-accent transition-colors hover:bg-accent-hover"
            >
              Start hiring
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

export function FinalCtaSection() {
  return (
    <section className="relative overflow-hidden border-t border-ink-100 bg-ink-900">
      <motion.div
        className="pointer-events-none absolute inset-0 opacity-30"
        aria-hidden
        animate={{
          backgroundPosition: ["0% 0%", "100% 100%"],
        }}
        transition={{ duration: 18, repeat: Infinity, repeatType: "reverse", ease: "linear" }}
        style={{
          backgroundImage:
            "radial-gradient(circle at 20% 50%, rgba(185,248,76,0.15), transparent 50%), radial-gradient(circle at 80% 50%, rgba(185,248,76,0.08), transparent 40%)",
          backgroundSize: "200% 200%",
        }}
      />

      <div className="relative mx-auto max-w-page px-6 py-20 text-center">
        <Reveal>
          <h2 className="text-h1 text-paper-0 md:text-[32px]">
            Your next role is one chat away.
          </h2>
          <p className="mx-auto mt-4 max-w-md text-body text-ink-500">
            Join from anywhere. Aarya adapts to your market, currency, and city —
            then gets to work.
          </p>
          <div className="mt-8 flex flex-col items-center gap-3">
            <LandingCta
              signedOutLabel="Start free"
              className="rounded-lg bg-accent px-8 py-3.5 text-body font-medium text-on-accent transition-transform hover:scale-[1.02] hover:bg-accent-hover"
            />
            <span className="text-micro text-ink-400">Free · No credit card · Cancel anytime</span>
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
