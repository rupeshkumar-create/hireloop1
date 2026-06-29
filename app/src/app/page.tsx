import Link from "next/link";
import {
  ArrowRight,
  Briefcase,
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
 * For logged-out visitors this sells the single idea behind Hireloop: you don't
 * fill in forms, you talk to Aarya. The hero pairs that promise with a live,
 * auto-playing chat demo and funnels straight into /signup → the chat-first
 * onboarding we land everyone in.
 *
 * Always accessible. If the visitor is already signed in we swap the primary
 * CTA to "Go to dashboard" so it doubles as a re-entry point.
 */
export default async function RootPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const primaryHref = user ? "/dashboard" : "/signup";
  const primaryLabel = user ? "Go to dashboard" : "Start chatting — it's free";

  return (
    <main className="min-h-screen bg-paper-0">
      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-20 border-b border-ink-100 bg-paper-0/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink-900">
              <span className="text-paper-0 text-h3 font-semibold">H</span>
            </span>
            <span className="text-h3 text-ink-900">Hireloop</span>
          </Link>

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
      <section className="mx-auto max-w-page px-6 pt-16 pb-20 md:pt-24">
        <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
          {/* Copy */}
          <div className="space-y-6">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-1 px-3 py-1 text-micro text-ink-500 ring-1 ring-ink-100">
              <Sparkles className="h-3 w-3 text-accent" strokeWidth={1.5} />
              India-first AI recruiting
            </span>

            <h1 className="text-display text-ink-900">
              Don&apos;t fill out forms.{" "}
              <span className="text-accent">Just talk to Aarya.</span>
            </h1>

            <p className="max-w-md text-body text-ink-700 leading-relaxed">
              Hireloop replaces the job-board grind with one conversation. Type
              or talk — Aarya finds live roles in India, scores your fit, and
              requests warm intros for you. One chat — matches, intros, and prep
              in the same place.
            </p>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link
                href={primaryHref}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-ink-900 px-6 py-3.5 text-body font-medium text-paper-0 transition-colors hover:bg-ink-700"
              >
                {primaryLabel}
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              </Link>
              <span className="inline-flex items-center gap-1.5 text-small text-ink-500">
                <Mic className="h-4 w-4 text-accent" strokeWidth={1.5} />
                Type or talk — your call
              </span>
            </div>

            <p className="text-micro text-ink-400">
              Free to start · LinkedIn sign-in · No credit card
            </p>
          </div>

          {/* Live chat demo */}
          <div className="md:pl-4">
            <ChatPreview />
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section className="border-t border-ink-100 bg-paper-1">
        <div className="mx-auto max-w-page px-6 py-16 md:py-20">
          <div className="mb-10 max-w-xl space-y-3">
            <h2 className="text-h1 text-ink-900">One chat does the whole job hunt</h2>
            <p className="text-body text-ink-700">
              Everything happens in the conversation. Aarya does the legwork in
              the background and shows you exactly what it did.
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
                body: "Aarya pulls live India roles, ranks your fit, and surfaces the strongest matches.",
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
                className="space-y-3 rounded-xl border border-ink-100 bg-paper-0 p-5"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink-900">
                    <Icon className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
                  </span>
                  <span className="text-micro text-ink-400">{step}</span>
                </div>
                <h3 className="text-h3 text-ink-900">{title}</h3>
                <p className="text-small text-ink-700 leading-relaxed">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ── Trust strip ──────────────────────────────────────────────────── */}
      <section className="mx-auto max-w-page px-6 py-16 md:py-20">
        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              Icon: Briefcase,
              title: "Live roles in India only",
              body: "Every match is a real, open role in India — no recycled global listings.",
            },
            {
              Icon: Zap,
              title: "See every action",
              body: "Aarya logs each step it takes on your behalf, so nothing happens in a black box.",
            },
            {
              Icon: ShieldCheck,
              title: "Your data stays yours",
              body: "Each profile is fully isolated and DPDP-aligned. We never cold-spam recruiters.",
            },
          ].map(({ Icon, title, body }) => (
            <div key={title} className="flex gap-3">
              <Icon className="mt-0.5 h-5 w-5 shrink-0 text-accent" strokeWidth={1.5} />
              <div className="space-y-1">
                <h3 className="text-h3 text-ink-900">{title}</h3>
                <p className="text-small text-ink-700 leading-relaxed">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────────── */}
      <section className="border-t border-ink-100 bg-paper-1">
        <div className="mx-auto max-w-page px-6 py-20 text-center">
          <div className="mx-auto max-w-xl space-y-6">
            <h2 className="text-h1 text-ink-900">
              Your next role is one conversation away
            </h2>
            <p className="text-body text-ink-700">
              Start chatting with Aarya now. Type or talk — it&apos;s the same
              copilot either way.
            </p>
            <Link
              href={primaryHref}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-ink-900 px-6 py-3.5 text-body font-medium text-paper-0 transition-colors hover:bg-ink-700"
            >
              {primaryLabel}
              <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t border-ink-100">
        <div className="mx-auto flex max-w-page flex-col items-center justify-between gap-3 px-6 py-8 text-micro text-ink-400 sm:flex-row">
          <span>© {new Date().getFullYear()} Hireloop · Made in India</span>
          <div className="flex items-center gap-4">
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
