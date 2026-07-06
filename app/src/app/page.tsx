import Link from "next/link";
import {
  Brain,
  Briefcase,
  FileText,
  GraduationCap,
  MessageSquare,
  Mic,
  Search,
  Send,
  ShieldCheck,
  Zap,
} from "@/components/brand/icons";
import { ChatPreviewLazy } from "@/components/landing/ChatPreviewLazy";
import { HeroAudience } from "@/components/landing/HeroAudience";
import { LandingCta } from "@/components/landing/LandingCta";
import { LandingNav } from "@/components/landing/LandingNav";

/**
 * App landing page (hireschema.com) — static shell, lazy hero demo, no auth gate.
 */
export const dynamic = "force-static";

export default function RootPage() {
  return (
    <main className="min-h-screen bg-paper-0">
      <LandingNav />

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section>
        <div className="mx-auto max-w-page px-6 pt-16 pb-16 md:pt-24">
          <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
            <HeroAudience />

            <div className="md:pl-4 landing-hero-in landing-hero-in-delay">
              <ChatPreviewLazy />
            </div>
          </div>
        </div>
      </section>

      {/* ── Credibility bar ──────────────────────────────────────────────── */}
      <section className="border-y border-ink-100 bg-paper-1">
        <div className="mx-auto grid max-w-page grid-cols-2 gap-6 px-6 py-8 md:grid-cols-4">
          {[
            { Icon: Mic, label: "Text or voice", sub: "Type or talk" },
            { Icon: Briefcase, label: "Live roles", sub: "Scored for fit" },
            { Icon: Send, label: "Warm intros", sub: "Not cold applies" },
            { Icon: Zap, label: "One chat", sub: "Search to intro" },
          ].map(({ Icon, label, sub }) => (
            <div key={label} className="flex items-start gap-3">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-accent" strokeWidth={1.5} />
              <div>
                <p className="text-small font-semibold text-ink-900">{label}</p>
                <p className="text-micro text-ink-500">{sub}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section id="how" className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="mb-10 max-w-xl space-y-3">
          <p className="text-micro font-semibold uppercase tracking-wide text-accent">
            How it works
          </p>
          <h2 className="text-h1 text-ink-900">One chat. The whole hunt.</h2>
          <p className="text-body text-ink-700">
            Aarya does the work and shows you every step.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              Icon: MessageSquare,
              step: "01",
              title: "Say what you want",
              body: "Role, location, pay — in plain words.",
            },
            {
              Icon: Search,
              step: "02",
              title: "It finds & scores",
              body: "Live roles in your market, ranked by fit.",
            },
            {
              Icon: Send,
              step: "03",
              title: "Get introduced",
              body: "Aarya hands you to the recruiter — no résumé void.",
            },
          ].map(({ Icon, step, title, body }) => (
            <div
              key={step}
              className="group space-y-3 rounded-xl border border-ink-100 bg-paper-1 p-6 transition-all duration-200 hover:-translate-y-1 hover:border-ink-300"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-ink-900 transition-transform duration-200 group-hover:scale-110">
                  <Icon className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
                </span>
                <span className="text-micro font-semibold text-ink-300">{step}</span>
              </div>
              <h3 className="text-h3 text-ink-900">{title}</h3>
              <p className="text-small text-ink-700 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Feature showcase ─────────────────────────────────────────────── */}
      <section id="features" className="border-t border-ink-100 bg-paper-1">
        <div className="mx-auto max-w-page px-6 py-16 md:py-24">
          <div className="mb-10 max-w-xl space-y-3">
            <p className="text-micro font-semibold uppercase tracking-wide text-accent">
              What you get
            </p>
            <h2 className="text-h1 text-ink-900">A recruiter, coach, and strategist.</h2>
            <p className="text-body text-ink-700">
              Your whole search — plus a plan for what&apos;s next.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                Icon: MessageSquare,
                title: "Chat, not forms",
                body: "Talk or type. Aarya builds your profile from your CV.",
              },
              {
                Icon: Briefcase,
                title: "Roles scored for you",
                body: "Real openings, ranked by genuine fit.",
              },
              {
                Icon: Send,
                title: "Warm intros",
                body: "Handed to the recruiter, not into the void.",
              },
              {
                Icon: FileText,
                title: "CV per role",
                body: "One click to a role-ready résumé.",
              },
              {
                Icon: GraduationCap,
                title: "Learning roadmap",
                body: "An hour-a-day plan to close any gap.",
              },
              {
                Icon: Brain,
                title: "Career intelligence",
                body: "Your value and next move — tied to real roles.",
              },
            ].map(({ Icon, title, body }) => (
              <div
                key={title}
                className="group space-y-3 rounded-xl border border-ink-100 bg-paper-0 p-6 transition-all duration-200 hover:-translate-y-1 hover:border-ink-300"
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-accent transition-transform duration-200 group-hover:scale-110">
                  <Icon className="h-5 w-5" strokeWidth={1.5} />
                </span>
                <h3 className="text-h3 text-ink-900">{title}</h3>
                <p className="text-small text-ink-700 leading-relaxed">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Trust ────────────────────────────────────────────────────────── */}
      <section id="trust" className="mx-auto max-w-page px-6 py-16 md:py-24">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div className="space-y-4">
            <p className="text-micro font-semibold uppercase tracking-wide text-accent">
              Trust
            </p>
            <h2 className="text-h1 text-ink-900">No black box. No spam.</h2>
            <p className="text-body text-ink-700 leading-relaxed">
              You see every action. Your profile is shared only when you say so.
            </p>
          </div>
          <div className="space-y-4">
            {[
              {
                Icon: Zap,
                title: "See every action",
                body: "Every step Aarya takes is logged.",
              },
              {
                Icon: ShieldCheck,
                title: "Your data stays yours",
                body: "Shared only with your consent. Never spammed.",
              },
            ].map(({ Icon, title, body }) => (
              <div
                key={title}
                className="flex gap-3 rounded-xl border border-ink-100 bg-paper-1 p-5 transition-colors duration-200 hover:border-ink-300"
              >
                <Icon className="mt-0.5 h-5 w-5 shrink-0 text-accent" strokeWidth={1.5} />
                <div className="space-y-1">
                  <h3 className="text-h3 text-ink-900">{title}</h3>
                  <p className="text-small text-ink-700 leading-relaxed">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── For recruiters ───────────────────────────────────────────────── */}
      <section id="recruiters" className="border-t border-ink-100 bg-paper-1">
        <div className="mx-auto max-w-page px-6 py-16 md:py-24">
          <div className="grid gap-10 md:grid-cols-2 md:items-center">
            <div className="space-y-4">
              <p className="text-micro font-semibold uppercase tracking-wide text-accent">
                For recruiters &amp; hiring managers
              </p>
              <h2 className="text-h1 text-ink-900">Hiring? Meet Nitya.</h2>
              <p className="text-body text-ink-700 leading-relaxed">
                Describe the role in plain words. Nitya surfaces pre-scored,
                genuinely-interested candidates and warms up the intro — so you
                skip cold sourcing and start conversations.
              </p>
              <Link
                href="/signup?role=recruiter"
                className="group inline-flex items-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-body font-medium text-on-accent transition-colors hover:bg-accent-hover"
              >
                Start hiring
                <Send className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" strokeWidth={1.5} />
              </Link>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {[
                { Icon: Search, title: "Describe the role", body: "Plain words — Nitya builds the brief." },
                { Icon: Zap, title: "Pre-scored matches", body: "Ranked candidates, not a résumé pile." },
                { Icon: Send, title: "Warm intros", body: "Candidates who opted in — not cold DMs." },
                { Icon: ShieldCheck, title: "Consent-first", body: "Profiles shared only with permission." },
              ].map(({ Icon, title, body }) => (
                <div
                  key={title}
                  className="group space-y-2 rounded-xl border border-ink-100 bg-paper-0 p-5 transition-all duration-200 hover:-translate-y-1 hover:border-ink-300"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent transition-transform duration-200 group-hover:scale-110">
                    <Icon className="h-4 w-4" strokeWidth={1.5} />
                  </span>
                  <h3 className="text-h3 text-ink-900">{title}</h3>
                  <p className="text-small text-ink-700 leading-relaxed">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="border-t border-ink-100 bg-ink-900">
        <div className="mx-auto max-w-page px-6 py-20 text-center">
          <div className="mx-auto max-w-xl space-y-6">
            <h2 className="text-h1 text-paper-0">
              Your next role is one chat away.
            </h2>
            <div className="flex flex-col items-center gap-3">
              <LandingCta
                signedOutLabel="Start free"
                className="rounded-lg bg-paper-0 px-6 py-3.5 text-body font-medium text-ink-900 transition-transform hover:scale-[1.02]"
              />
              <span className="text-micro text-paper-0/50">
                Free · No credit card
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t border-ink-100">
        <div className="mx-auto flex max-w-page flex-col items-center justify-between gap-3 px-6 py-8 text-micro text-ink-400 sm:flex-row">
          <span>© {new Date().getFullYear()} Hireschema</span>
          <div className="flex items-center gap-4">
            <a href="#how" className="transition-colors hover:text-ink-700">
              How it works
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
    </main>
  );
}
