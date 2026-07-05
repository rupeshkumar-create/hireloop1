"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Check, Sparkles } from "@/components/brand/icons";
import { cn } from "@/lib/utils";

/**
 * Audience-aware hero. A visitor picks their side (candidate / recruiter) and
 * the whole pitch swaps — so both a job seeker and a hiring manager see a
 * headline written for them the moment they land.
 */
type Audience = "candidate" | "recruiter";

const CONTENT: Record<
  Audience,
  {
    eyebrow: string;
    lead: string;
    accent: string;
    sub: string;
    checks: string[];
    ctaLabel: string;
    ctaHref: string;
    secondaryLabel: string;
  }
> = {
  candidate: {
    eyebrow: "For job seekers · India, US & UK",
    lead: "Stop applying.",
    accent: "Get introduced.",
    sub: "Aarya is your AI recruiter. It finds live roles, scores your fit, tailors your CV, and gets you a warm intro — in one chat.",
    checks: ["Free to start", "LinkedIn or email", "No credit card"],
    ctaLabel: "Find my next role",
    ctaHref: "/signup",
    secondaryLabel: "How it works",
  },
  recruiter: {
    eyebrow: "For recruiters & hiring managers",
    lead: "Skip the sourcing.",
    accent: "Get shortlists.",
    sub: "Nitya is your AI sourcer. Describe the role and it surfaces pre-scored, genuinely-interested candidates — with warm intros, not cold outreach.",
    checks: ["Pre-scored fit", "Interested candidates", "No cold sourcing"],
    ctaLabel: "Start hiring",
    ctaHref: "/signup?role=recruiter",
    secondaryLabel: "See how it works",
  },
};

export function HeroAudience() {
  const [audience, setAudience] = useState<Audience>("candidate");
  const c = CONTENT[audience];

  return (
    <div className="space-y-6 landing-hero-in">
      {/* Audience toggle */}
      <div className="inline-flex rounded-full bg-paper-1 p-1 text-small ring-1 ring-ink-100">
        {(["candidate", "recruiter"] as Audience[]).map((a) => (
          <button
            key={a}
            type="button"
            onClick={() => setAudience(a)}
            aria-pressed={audience === a}
            className={cn(
              "rounded-full px-4 py-1.5 font-medium transition-colors duration-fast",
              audience === a
                ? "bg-accent text-on-accent"
                : "text-ink-500 hover:text-ink-900",
            )}
          >
            {a === "candidate" ? "I'm a candidate" : "I'm a recruiter"}
          </button>
        ))}
      </div>

      <span className="flex items-center gap-1.5 text-micro font-medium text-ink-500">
        <Sparkles className="h-3 w-3 text-accent" strokeWidth={1.5} />
        {c.eyebrow}
      </span>

      <h1 className="text-display text-ink-900">
        {c.lead} <span className="text-accent">{c.accent}</span>
      </h1>

      <p className="max-w-md text-body text-ink-700 leading-relaxed">{c.sub}</p>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Link
          href={c.ctaHref}
          className="group inline-flex items-center justify-center gap-2 rounded-lg bg-accent px-6 py-3.5 text-body font-medium text-on-accent transition-colors hover:bg-accent-hover"
        >
          {c.ctaLabel}
          <ArrowRight
            className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5"
            strokeWidth={1.5}
          />
        </Link>
        <a
          href="#how"
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-ink-200 px-6 py-3.5 text-body font-medium text-ink-800 transition-colors hover:bg-ink-50"
        >
          {c.secondaryLabel}
        </a>
      </div>

      <ul className="flex flex-wrap gap-x-5 gap-y-2 pt-1">
        {c.checks.map((item) => (
          <li
            key={item}
            className="inline-flex items-center gap-1.5 text-micro text-ink-500"
          >
            <Check className="h-3.5 w-3.5 text-accent" strokeWidth={2} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
