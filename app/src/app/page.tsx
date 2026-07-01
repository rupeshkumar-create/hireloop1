import Link from "next/link";
import {
  ArrowRight,
  Brain,
  Briefcase,
  Check,
  FileText,
  GraduationCap,
  MessageSquare,
  Mic,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { createClient } from "@/lib/supabase/server";
import { ChatPreview } from "@/components/landing/ChatPreview";

/**
 * App landing page (app.hireloop.in) — chat-first.
 *
 * Sells the single idea behind Hireloop: you don't fill in forms, you talk to
 * Aarya — and it does the whole hunt (find → score → tailor → introduce). The
 * hero pairs that promise with a live, auto-playing chat demo and funnels into
 * /signup. If the visitor is already signed in, CTAs point at /dashboard.
 */
export default async function RootPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const primaryHref = user ? "/dashboard" : "/signup";
  const primaryLabel = user ? "Go to dashboard" : "Start free — takes a minute";

  return (
    <main className="min-h-screen bg-paper-0">
      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-ink-100 bg-paper-0/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-900">
              <span className="text-paper-0 text-h3 font-semibold">H</span>
            </span>
            <span className="text-h3 text-ink-900">Hireloop</span>
          </Link>

          <nav className="hidden items-center gap-6 md:flex">
            <a href="#how" className="text-small text-ink-600 transition-colors hover:text-ink-900">
              How it works
            </a>
            <a href="#features" className="text-small text-ink-600 transition-colors hover:text-ink-900">
              What you get
            </a>
            <a href="#trust" className="text-small text-ink-600 transition-colors hover:text-ink-900">
              Why trust it
            </a>
          </nav>

          <div className="flex items-center gap-2">
            {!user && (
              <Link
                href="/login"
                className="rounded-md px-3 py-2 text-small font-medium text-ink-700 transition-colors hover:bg-ink-50"
              >
                Log in
              </Link>
            )}
            <Link
              href={primaryHref}
              className="inline-flex items-center gap-1.5 rounded-md bg-ink-900 px-4 py-2 text-small font-medium text-paper-0 transition-colors hover:bg-ink-700"
            >
              {user ? "Dashboard" : "Sign up"}
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        {/* decorative accent glow */}
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 h-[420px] w-[820px] -translate-x-1/2 rounded-full opacity-[0.14] blur-3xl"
          style={{
            background:
              "radial-gradient(closest-side, var(--color-accent, #6366f1), transparent)",
          }}
        />
        <div className="relative mx-auto max-w-page px-6 pt-16 pb-16 md:pt-24">
          <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
            {/* Copy */}
            <div className="space-y-6">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-1 px-3 py-1 text-micro font-medium text-ink-600 ring-1 ring-ink-100">
                <Sparkles className="h-3 w-3 text-accent" strokeWidth={1.5} />
                AI recruiting for India, the US &amp; the UK
              </span>

              <h1 className="text-display text-ink-900">
                Don&apos;t apply into the void.{" "}
                <span className="text-accent">Get introduced.</span>
              </h1>

              <p className="max-w-md text-body text-ink-700 leading-relaxed">
                Aarya is your AI recruiter. Tell it what you want — by text or
                voice — and it finds live roles, scores your fit, tailors your
                CV, and hands you a warm intro. The whole hunt, in one chat.
              </p>

              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Link
                  href={primaryHref}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-ink-900 px-6 py-3.5 text-body font-medium text-paper-0 transition-colors hover:bg-ink-700"
                >
                  {primaryLabel}
                  <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
                </Link>
                <a
                  href="#how"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-ink-200 px-6 py-3.5 text-body font-medium text-ink-800 transition-colors hover:bg-ink-50"
                >
                  See how it works
                </a>
              </div>

              <ul className="flex flex-wrap gap-x-5 gap-y-2 pt-1">
                {[
                  "Free to start",
                  "LinkedIn or email sign-in",
                  "No credit card",
                ].map((item) => (
                  <li key={item} className="inline-flex items-center gap-1.5 text-micro text-ink-500">
                    <Check className="h-3.5 w-3.5 text-accent" strokeWidth={2} />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Live chat demo */}
            <div className="md:pl-4">
              <ChatPreview />
            </div>
          </div>
        </div>
      </section>

      {/* ── Credibility bar ──────────────────────────────────────────────── */}
      <section className="border-y border-ink-100 bg-paper-1">
        <div className="mx-auto grid max-w-page grid-cols-2 gap-6 px-6 py-8 md:grid-cols-4">
          {[
            { Icon: Mic, label: "Text or voice", sub: "Same copilot either way" },
            { Icon: Briefcase, label: "Live roles", sub: "Real openings, scored for fit" },
            { Icon: Send, label: "Warm intros", sub: "Not cold applications" },
            { Icon: Zap, label: "In one chat", sub: "Find, tailor, apply, prep" },
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
          <h2 className="text-h1 text-ink-900">One chat does the whole job hunt</h2>
          <p className="text-body text-ink-700">
            Everything happens in the conversation. Aarya does the legwork in the
            background — and shows you exactly what it did.
          </p>
        </div>

        <ol className="grid gap-6 md:grid-cols-3">
          {[
            {
              Icon: MessageSquare,
              step: "01",
              title: "Tell Aarya what you want",
              body: "Role, location, salary, must-haves — in plain words, by text or voice.",
            },
            {
              Icon: Search,
              step: "02",
              title: "It searches & scores",
              body: "Aarya pulls live roles in your market, ranks your fit, and surfaces the strongest matches.",
            },
            {
              Icon: Send,
              step: "03",
              title: "Warm intros, not cold applies",
              body: "Ask for an intro and Aarya hands it to the recruiter — you skip the résumé void.",
            },
          ].map(({ Icon, step, title, body }) => (
            <li
              key={step}
              className="space-y-3 rounded-xl border border-ink-100 bg-paper-1 p-6"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-ink-900">
                  <Icon className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
                </span>
                <span className="text-micro font-semibold text-ink-300">{step}</span>
              </div>
              <h3 className="text-h3 text-ink-900">{title}</h3>
              <p className="text-small text-ink-700 leading-relaxed">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* ── Feature showcase ─────────────────────────────────────────────── */}
      <section id="features" className="border-t border-ink-100 bg-paper-1">
        <div className="mx-auto max-w-page px-6 py-16 md:py-24">
          <div className="mb-10 max-w-xl space-y-3">
            <p className="text-micro font-semibold uppercase tracking-wide text-accent">
              What you get
            </p>
            <h2 className="text-h1 text-ink-900">A recruiter, a coach, and a career strategist</h2>
            <p className="text-body text-ink-700">
              Not another job board. Aarya works your search end to end — and
              helps you grow into the roles you want next.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                Icon: MessageSquare,
                title: "Conversational, not forms",
                body: "Talk or type. No endless fields — Aarya builds your profile from your CV and the chat.",
              },
              {
                Icon: Briefcase,
                title: "Real roles, scored for you",
                body: "Actual open roles in your market, ranked by genuine fit — never recycled global listings.",
              },
              {
                Icon: Send,
                title: "Warm intros",
                body: "Ask, and Aarya hands your profile to the recruiter — instead of a one-way application.",
              },
              {
                Icon: FileText,
                title: "CV tailored per role",
                body: "One click turns your résumé into a role-specific, recruiter-ready version for each job.",
              },
              {
                Icon: GraduationCap,
                title: "Personal learning roadmap",
                body: "A résumé-aware, hour-a-day plan to close the gap to any role — with progress tracking.",
              },
              {
                Icon: Brain,
                title: "Career intelligence",
                body: "Your archetype, market value, and likely next move — each tied to roles you can act on.",
              },
            ].map(({ Icon, title, body }) => (
              <div
                key={title}
                className="group space-y-3 rounded-xl border border-ink-100 bg-paper-0 p-6 transition-colors hover:border-ink-200"
              >
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-accent">
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
              Why trust it
            </p>
            <h2 className="text-h1 text-ink-900">No black box. No spam.</h2>
            <p className="text-body text-ink-700 leading-relaxed">
              Aarya works for you, in the open. You see every action it takes,
              and your profile is only shared when you say so.
            </p>
          </div>
          <div className="space-y-4">
            {[
              {
                Icon: Zap,
                title: "See every action",
                body: "Aarya logs each step it takes on your behalf, so nothing happens behind your back.",
              },
              {
                Icon: ShieldCheck,
                title: "Your data stays yours",
                body: "Your profile is fully isolated and shared only with your consent. We never cold-spam recruiters.",
              },
            ].map(({ Icon, title, body }) => (
              <div key={title} className="flex gap-3 rounded-xl border border-ink-100 bg-paper-1 p-5">
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

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="border-t border-ink-100 bg-ink-900">
        <div className="mx-auto max-w-page px-6 py-20 text-center">
          <div className="mx-auto max-w-xl space-y-6">
            <h2 className="text-h1 text-paper-0">
              Your next role is one conversation away
            </h2>
            <p className="text-body text-paper-0/70">
              Start chatting with Aarya now. Type or talk — it&apos;s the same
              copilot either way.
            </p>
            <div className="flex flex-col items-center gap-3">
              <Link
                href={primaryHref}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-paper-0 px-6 py-3.5 text-body font-medium text-ink-900 transition-transform hover:scale-[1.02]"
              >
                {primaryLabel}
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              </Link>
              <span className="text-micro text-paper-0/50">
                Free to start · No credit card
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t border-ink-100">
        <div className="mx-auto flex max-w-page flex-col items-center justify-between gap-3 px-6 py-8 text-micro text-ink-400 sm:flex-row">
          <span>© {new Date().getFullYear()} Hireloop</span>
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
