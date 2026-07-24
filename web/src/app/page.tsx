/**
 * Hireschema marketing landing — DESIGN.md v2.
 * Gmail warm-intro wedge. Dark charcoal. One product beat, one human moment.
 */

import Link from "next/link";
import {
  ArrowRight,
  Briefcase,
  Mail,
  MessageCircle,
  Percent,
  Users,
} from "lucide-react";
import { ProductPreview } from "@/components/marketing/ProductPreview";
import { Reveal } from "@/components/ui/Reveal";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://hireschema.com";

export const metadata = {
  title: "Hireschema — Get introduced to the hiring manager",
  description:
    "Aarya finds India-eligible roles, scores your fit, and sends a warm intro from your Gmail to the hiring manager. Free for candidates. Private beta.",
};

// ── Hero ─────────────────────────────────────────────────────────────────────

function Hero() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-20 sm:py-28">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div>
            <Reveal>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ink-50 border border-ink-100 mb-8">
                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                <span className="text-micro text-ink-500 uppercase">
                  Private beta · 50 seats left this month
                </span>
              </div>
            </Reveal>

            <Reveal delay={60}>
              <h1 className="text-display text-ink-900 mb-6 leading-[1.05]">
                Get introduced to the hiring manager.
                <span className="text-ink-500"> From your Gmail.</span>
              </h1>
            </Reveal>

            <Reveal delay={120}>
              <p className="text-h3 text-ink-500 font-normal leading-relaxed mb-10 max-w-prose">
                Aarya scores live India roles against your profile, drafts the
                intro in your voice, and sends it through{" "}
                <em className="not-italic text-ink-700">your</em> Gmail — after
                you approve every word.
              </p>
            </Reveal>

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
              <p className="mt-5 text-small text-ink-400">
                Outreach goes through your Gmail account — your reputation, your
                control.
              </p>
            </Reveal>
          </div>

          <Reveal delay={120}>
            <ProductPreview variant="candidate" className="lg:max-w-none" />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ── Intro email (human moment) ───────────────────────────────────────────────

function IntroEmailSnippet() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-20">
        <div className="grid lg:grid-cols-2 gap-12 items-start">
          <Reveal>
            <div className="max-w-prose">
              <p className="text-micro text-ink-500 uppercase mb-3">
                What actually gets sent
              </p>
              <h2 className="text-h1 text-ink-900 leading-tight mb-4">
                A real intro, not a template blast.
              </h2>
              <p className="text-body text-ink-500 leading-relaxed">
                You review the draft. You edit it. It sends from{" "}
                <span className="text-ink-700">you@gmail.com</span> — so the HM
                sees a person, not a platform.
              </p>
            </div>
          </Reveal>

          <Reveal delay={90}>
            <div className="bg-paper-1 border border-ink-100 rounded-lg overflow-hidden font-mono text-small">
              <div className="border-b border-ink-100 px-4 py-3 space-y-1.5 bg-ink-50">
                <p className="text-ink-500">
                  <span className="text-ink-400">From:</span>{" "}
                  <span className="text-ink-700">priya.sharma@gmail.com</span>
                </p>
                <p className="text-ink-500">
                  <span className="text-ink-400">To:</span>{" "}
                  <span className="text-ink-700">[HM — Razorpay Payments]</span>
                </p>
                <p className="text-ink-500">
                  <span className="text-ink-400">Subject:</span>{" "}
                  <span className="text-ink-700">
                    Senior Backend Engineer — quick intro
                  </span>
                </p>
              </div>
              <div className="px-4 py-5 text-ink-600 leading-relaxed space-y-3">
                <p>Hi [Name],</p>
                <p>
                  I saw your team is hiring for the Backend Engineer role posted
                  last Tuesday. I&apos;ve spent six years on Go and Kafka at
                  [•••] — Aarya flagged an 87% match on skills and comp band.
                </p>
                <p>Would you have 15 minutes this week for a quick chat?</p>
                <p>— Priya</p>
              </div>
              <div className="border-t border-ink-100 px-4 py-2.5 text-micro text-ink-400">
                Redacted beta example · candidate-approved before send
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

// ── Three-step "How it works" ────────────────────────────────────────────────

const STEPS = [
  {
    icon: MessageCircle,
    n: "01",
    title: "Tell Aarya about you",
    body: "Upload your resume or paste your LinkedIn. Aarya understands your skills, seniority, salary expectations, and the roles you actually want.",
  },
  {
    icon: Percent,
    n: "02",
    title: "See your match score — and why",
    body: "Every live role gets a 0–100% score with a plain-English breakdown: skills, experience, location, compensation. You decide before anything gets sent.",
  },
  {
    icon: Mail,
    n: "03",
    title: "Approve the intro. Send from Gmail.",
    body: "Nitya finds the hiring manager, drafts the email in your voice, and sends it via your Gmail after you sign off. No spam. No cold templates.",
  },
];

function HowItWorks() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-20">
        <Reveal>
          <div className="max-w-prose mb-14">
            <p className="text-micro text-ink-500 uppercase mb-3">
              How it works
            </p>
            <h2 className="text-h1 text-ink-900 leading-tight">
              Chat → match → intro. That&apos;s it.
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
                  <Icon className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                </div>
                <h3 className="text-h3 text-ink-900 leading-snug">
                  {step.title}
                </h3>
                <p className="text-body text-ink-500 leading-relaxed">
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
      <div className="max-w-page mx-auto px-6 py-20">
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
              title="Your hiring pipeline, in one chat."
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
    <article className="bg-paper-1 border border-ink-100 rounded-lg p-8 hover:border-ink-200 transition-colors duration-base">
      <div className="flex items-center gap-2 mb-6">
        <Icon className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
        <span className="text-micro text-ink-500 uppercase">{tag}</span>
      </div>

      <h3 className="text-h1 text-ink-900 mb-6 leading-tight">{title}</h3>

      <ul className="space-y-3 mb-8">
        {bullets.map((b) => (
          <li key={b} className="flex items-start gap-3 text-body text-ink-500">
            <span className="mt-2 w-1 h-1 rounded-full bg-accent shrink-0" />
            <span className="leading-relaxed">{b}</span>
          </li>
        ))}
      </ul>

      <Link
        href={href}
        className="
          inline-flex items-center gap-1.5 text-body font-medium
          text-ink-700 hover:text-accent transition-colors duration-fast
        "
      >
        {cta}
        <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
      </Link>
    </article>
  );
}

// ── Principles (trimmed) ─────────────────────────────────────────────────────

function Principles() {
  const items = [
    {
      title: "From your Gmail, not ours",
      body: "Cold outreach goes through your account. Your reputation, your relationships, your control.",
    },
    {
      title: "India-only marketplace",
      body: "Indian candidates, Indian recruiters, salaries in INR. No global spray-and-pray.",
    },
    {
      title: "Two AIs, one database",
      body: "Aarya and Nitya share state through Postgres — auditable, reproducible, no black-box handoffs.",
    },
  ];

  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-20">
        <Reveal>
          <div className="max-w-prose mb-12">
            <p className="text-micro text-ink-500 uppercase mb-3">
              Why it works
            </p>
            <h2 className="text-h1 text-ink-900 leading-tight">
              Built for trust, not volume.
            </h2>
          </div>
        </Reveal>

        <div className="grid sm:grid-cols-3 gap-8">
          {items.map((item, i) => (
            <Reveal key={item.title} delay={i * 90} className="space-y-2">
              <h3 className="text-h3 text-ink-900">{item.title}</h3>
              <p className="text-body text-ink-500 leading-relaxed">
                {item.body}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Founder note ─────────────────────────────────────────────────────────────

function FounderNote() {
  return (
    <section className="border-b border-ink-100">
      <div className="max-w-page mx-auto px-6 py-20">
        <Reveal>
          <blockquote className="max-w-prose border-l-2 border-accent pl-6">
            <p className="text-h3 text-ink-700 font-normal leading-relaxed mb-4">
              &ldquo;We built this because applying into ATS black holes is
              broken — especially in India. The intro email is the product. Everything
              else is just getting you to a good one.&rdquo;
            </p>
            <footer className="text-small text-ink-500">
              — Rupesh, founder ·{" "}
              <a
                href="mailto:hello@hireschema.com"
                className="text-ink-700 hover:text-accent transition-colors"
              >
                hello@hireschema.com
              </a>
            </footer>
          </blockquote>
        </Reveal>
      </div>
    </section>
  );
}

// ── CTA strip ────────────────────────────────────────────────────────────────

function CtaStrip() {
  return (
    <section>
      <div className="max-w-page mx-auto px-6 py-20">
        <Reveal>
          <div className="bg-paper-1 border border-ink-100 rounded-lg p-12 md:p-16 text-center">
            <h2 className="text-h1 text-ink-900 mb-4 leading-tight">
              50 candidate seats this month.
            </h2>
            <p className="text-body text-ink-500 mb-8 max-w-prose mx-auto leading-relaxed">
              We&apos;re onboarding slowly so every intro gets a human review.
              Free for candidates, forever. Recruiters —{" "}
              <a
                href="mailto:hello@hireschema.com"
                className="text-ink-700 hover:text-accent transition-colors"
              >
                email us
              </a>{" "}
              to get on the list.
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
                Claim a beta seat
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              </Link>
              <Link
                href="mailto:hello@hireschema.com"
                className="
                  inline-flex items-center justify-center gap-2
                  bg-ink-50 hover:bg-ink-100 text-ink-900
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
      <IntroEmailSnippet />
      <HowItWorks />
      <ForWhom />
      <Principles />
      <FounderNote />
      <CtaStrip />
    </main>
  );
}
