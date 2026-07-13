/**
 * Hireschema marketing landing — DESIGN.md compliant.
 *
 * North star: Stripe Docs + Linear. Type-led, quiet, confident.
 * No dark hero. No gradient orbs. No floating UI mockups.
 * The content (what Aarya does) is the design.
 */

import Link from "next/link";
import {
  ArrowRight,
  Briefcase,
  Search,
  Send,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";
import { Reveal } from "@/components/ui/Reveal";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://hireschema.com";

export const metadata = {
  title: "Hireschema — Your AI career partner",
  description:
    "Aarya finds India-eligible roles, scores your fit, and helps you make a warm intro to the hiring manager. Free for candidates. Private beta.",
};

// ── Hero ─────────────────────────────────────────────────────────────────────

function Hero() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-24 sm:py-32">
        <div className="max-w-2xl">
          {/* Status pill */}
          <Reveal>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ink-50 border border-ink-100 mb-8">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <span className="text-micro text-ink-700 uppercase">
                Private beta · India · 2026
              </span>
            </div>
          </Reveal>

          {/* Headline — type carries everything */}
          <Reveal delay={60}>
            <h1 className="text-display text-ink-900 mb-6 leading-[1.05]">
              Your AI career partner
              <span className="text-ink-500">, built for India.</span>
            </h1>
          </Reveal>

          {/* Subhead */}
          <Reveal delay={120}>
            <p className="text-h3 text-ink-700 font-normal leading-relaxed mb-10 max-w-prose">
              Aarya finds you the right roles, scores your match, and sends a
              warm intro from <em className="not-italic text-ink-900">your</em>{" "}
              Gmail to the hiring manager. One chat. Zero applications shouted
              into the void.
            </p>
          </Reveal>

          {/* CTAs */}
          <Reveal delay={180}>
          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              href={APP_URL + "/signup?role=candidate"}
              className="
                inline-flex items-center justify-center gap-2
                bg-accent hover:bg-accent-hover text-accent-fg
                text-body font-medium px-5 h-12 rounded-md
                transition-colors duration-fast
              "
            >
              Chat with Aarya
              <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
            </Link>
            <Link
              href={APP_URL + "/signup?role=recruiter"}
              className="
                inline-flex items-center justify-center gap-2
                bg-ink-50 hover:bg-ink-100 text-ink-900
                text-body font-medium px-5 h-12 rounded-md
                transition-colors duration-fast
              "
            >
              Hire with Nitya
            </Link>
          </div>
          </Reveal>

          <Reveal delay={240}>
            <p className="mt-5 text-small text-ink-500">
              +91 / +1 / +44 · No credit card · DPDP Act 2023 compliant
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ── Three-step "How it works" ────────────────────────────────────────────────

const STEPS = [
  {
    icon: Sparkles,
    n: "01",
    title: "Tell Aarya about you",
    body: "Upload your resume or paste your LinkedIn. Aarya understands your skills, seniority, salary expectations, and the roles you actually want.",
  },
  {
    icon: Search,
    n: "02",
    title: "Get matched, ranked, explained",
    body: "Aarya scores every live role in your market against your profile. You see why each match works — skills, experience, location, compensation — before you decide.",
  },
  {
    icon: Send,
    n: "03",
    title: "Warm intro, sent from your Gmail",
    body: "Pick a role. Nitya (our recruiter AI) finds the hiring manager, drafts a personalised email from your point of view, and sends it via your Gmail. No spam. No cold templates.",
  },
];

function HowItWorks() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-24">
        <Reveal>
          <div className="max-w-prose mb-16">
            <p className="text-micro text-ink-500 uppercase mb-3">
              How it works
            </p>
            <h2 className="text-h1 text-ink-900 leading-tight">
              Three steps. No spam. No ghosting.
            </h2>
          </div>
        </Reveal>

        <div className="grid sm:grid-cols-3 gap-8">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <Reveal key={step.n} delay={i * 90} className="space-y-4">
                <div className="flex items-center gap-3">
                  <span className="text-micro text-ink-500 uppercase">
                    {step.n}
                  </span>
                  <span className="h-px flex-1 bg-ink-100" />
                  <Icon
                    className="h-4 w-4 text-ink-500"
                    strokeWidth={1.5}
                  />
                </div>
                <h3 className="text-h3 text-ink-900 leading-snug">
                  {step.title}
                </h3>
                <p className="text-body text-ink-700 leading-relaxed">
                  {step.body}
                </p>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ── Two-up: Candidates vs Recruiters ─────────────────────────────────────────

function ForWhom() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-24">
        <div className="grid md:grid-cols-2 gap-6">
          <Reveal>
            <PathCard
              tag="For candidates"
              icon={Briefcase}
              title="Stop applying. Start being found."
              bullets={[
                "Every match scored 0–100% with a plain-English why",
                "Warm intros sent from your Gmail — full editorial control",
                "Tailored resume PDF per role, in 20 seconds",
                "Voice mode with Aarya (en-IN, Hinglish-aware)",
              ]}
              cta="Start with Aarya"
              href={APP_URL + "/signup?role=candidate"}
            />
          </Reveal>
          <Reveal delay={100}>
            <PathCard
              tag="For recruiters"
              icon={Users}
              title="A recruiter that never sleeps."
              bullets={[
                "Nitya intakes your role through a conversation",
                "Finds + ranks candidates from your private pipeline + ours",
                "Drafts personalised outreach you approve in one click",
                "Tracks replies, scheduling, and pipeline state",
              ]}
              cta="Try with Nitya"
              href={APP_URL + "/signup?role=recruiter"}
            />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function PathCard({
  tag,
  icon: Icon,
  title,
  bullets,
  cta,
  href,
}: {
  tag: string;
  icon: typeof Briefcase;
  title: string;
  bullets: string[];
  cta: string;
  href: string;
}) {
  return (
    <article className="bg-paper-1 border border-ink-100 rounded-lg p-8 hover:shadow-2 transition-shadow duration-base">
      <div className="flex items-center gap-2 mb-6">
        <Icon className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
        <span className="text-micro text-ink-500 uppercase">{tag}</span>
      </div>

      <h3 className="text-h1 text-ink-900 mb-6 leading-tight">{title}</h3>

      <ul className="space-y-3 mb-8">
        {bullets.map((b) => (
          <li key={b} className="flex items-start gap-3 text-body text-ink-700">
            <span className="mt-2 w-1 h-1 rounded-full bg-accent shrink-0" />
            <span className="leading-relaxed">{b}</span>
          </li>
        ))}
      </ul>

      <Link
        href={href}
        className="
          inline-flex items-center gap-1.5 text-body font-medium
          text-ink-900 hover:text-accent transition-colors duration-fast
        "
      >
        {cta}
        <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
      </Link>
    </article>
  );
}

// ── Defensible-moats strip ───────────────────────────────────────────────────

function Principles() {
  const items = [
    {
      title: "From your Gmail, not ours",
      body: "Cold outreach goes through your account. Your reputation, your relationships, your control.",
    },
    {
      title: "India-locked by design",
      body: "+91 phone verification, country_code = IN in every query, data resident in ap-south-1.",
    },
    {
      title: "Two AIs, one DB",
      body: "Aarya and Nitya communicate only through Postgres state. Auditable, reproducible, no agent-to-agent spaghetti.",
    },
    {
      title: "DPDP Act 2023, day one",
      body: "Bias audit on every match score. Consent logged per use. Right to delete + export, end-to-end.",
    },
  ];

  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-24">
        <Reveal>
          <div className="max-w-prose mb-12">
            <p className="text-micro text-ink-500 uppercase mb-3">
              Built the right way
            </p>
            <h2 className="text-h1 text-ink-900 leading-tight">
              Boring infrastructure. Magical outcomes.
            </h2>
          </div>
        </Reveal>

        <div className="grid sm:grid-cols-2 gap-6">
          {items.map((item, i) => (
            <Reveal
              key={item.title}
              delay={(i % 2) * 90}
              className="flex items-start gap-4 py-3"
            >
              <Zap
                className="h-4 w-4 text-accent shrink-0 mt-1"
                strokeWidth={1.5}
              />
              <div>
                <h3 className="text-h3 text-ink-900 mb-1">{item.title}</h3>
                <p className="text-body text-ink-700 leading-relaxed">
                  {item.body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── CTA strip ────────────────────────────────────────────────────────────────

function CtaStrip() {
  return (
    <section>
      <div className="max-w-page mx-auto px-6 py-24">
        <Reveal>
        <div className="bg-ink-900 text-paper-0 rounded-xl p-12 md:p-16 text-center">
          <h2 className="text-h1 text-paper-0 mb-4 leading-tight">
            Stop applying.
            <br />
            Start being found.
          </h2>
          <p className="text-body text-ink-300 mb-8 max-w-prose mx-auto leading-relaxed">
            Aarya is in private beta. Free for candidates, forever.
            Join the waitlist or talk to us about hiring.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href={APP_URL + "/signup?role=candidate"}
              className="
                inline-flex items-center justify-center gap-2
                bg-accent hover:bg-accent-hover text-accent-fg
                text-body font-medium px-5 h-12 rounded-md
                transition-colors duration-fast
              "
            >
              Chat with Aarya
              <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
            </Link>
            <Link
              href="mailto:hello@hireschema.com"
              className="
                inline-flex items-center justify-center gap-2
                bg-ink-700 hover:bg-ink-700/80 text-paper-0
                text-body font-medium px-5 h-12 rounded-md
                transition-colors duration-fast
              "
            >
              Talk to us about hiring
            </Link>
          </div>
        </div>
        </Reveal>
      </div>
    </section>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function HomePage() {
  return (
    <main className="bg-paper-0">
      <Hero />
      <HowItWorks />
      <ForWhom />
      <Principles />
      <CtaStrip />
    </main>
  );
}
