"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { ArrowRight, Check, Sparkles } from "@/components/brand/icons";
import { ChatPreviewLazy } from "@/components/landing/ChatPreviewLazy";
import { FadeUp, Stagger, StaggerItem } from "@/components/ui/motion";
import { cn } from "@/lib/utils";

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
  }
> = {
  candidate: {
    eyebrow: "AI recruiting for job seekers worldwide",
    lead: "Stop spraying résumés.",
    accent: "Start getting introduced.",
    sub: "Tell Aarya what you want — in text or voice. It reads your CV, finds live roles in your city and country, scores your fit, and requests warm intros on your behalf. One chat, end to end.",
    checks: ["Free to start", "Works in 15+ markets", "No credit card"],
    ctaLabel: "Find my next role",
    ctaHref: "/signup",
  },
  recruiter: {
    eyebrow: "AI sourcing for hiring teams",
    lead: "Stop cold outreach.",
    accent: "Start warm conversations.",
    sub: "Describe the role to Nitya in plain language. It surfaces pre-scored candidates who already opted in — then warms up the intro so you skip the résumé pile and talk to people who want the job.",
    checks: ["Pre-scored fit", "Consent-first", "No spam"],
    ctaLabel: "Start hiring",
    ctaHref: "/signup?role=recruiter",
  },
};

const copyVariants = {
  enter: { opacity: 0, y: 12 },
  center: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

export function HeroSection() {
  const [audience, setAudience] = useState<Audience>("candidate");
  const c = CONTENT[audience];

  return (
    <section className="relative overflow-hidden">
      {/* Ambient grid */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        aria-hidden
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(185,248,76,0.06) 1px, transparent 1px), linear-gradient(to bottom, rgba(185,248,76,0.04) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse 80% 60% at 50% 0%, black, transparent)",
        }}
      />

      <div className="relative mx-auto max-w-page px-6 pb-16 pt-14 md:pb-24 md:pt-20">
        <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
          <Stagger className="space-y-6" delay={0.05}>
            <StaggerItem>
              <div className="inline-flex rounded-full bg-paper-1 p-1 text-small ring-1 ring-ink-100">
                {(["candidate", "recruiter"] as Audience[]).map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => setAudience(a)}
                    aria-pressed={audience === a}
                    className={cn(
                      "relative rounded-full px-4 py-1.5 font-medium transition-colors duration-fast",
                      audience === a ? "text-on-accent" : "text-ink-500 hover:text-ink-900",
                    )}
                  >
                    {audience === a ? (
                      <motion.span
                        layoutId="audience-pill"
                        className="absolute inset-0 rounded-full bg-accent"
                        transition={{ type: "spring", stiffness: 420, damping: 32 }}
                      />
                    ) : null}
                    <span className="relative z-10">
                      {a === "candidate" ? "I'm a candidate" : "I'm a recruiter"}
                    </span>
                  </button>
                ))}
              </div>
            </StaggerItem>

            <StaggerItem>
              <AnimatePresence mode="wait">
                <motion.div
                  key={audience}
                  variants={copyVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={{ duration: 0.28, ease: [0.21, 0.47, 0.32, 0.98] }}
                  className="space-y-5"
                >
                  <span className="inline-flex items-center gap-1.5 text-micro font-medium text-ink-500">
                    <Sparkles className="h-3 w-3 text-accent" strokeWidth={1.5} />
                    {c.eyebrow}
                  </span>

                  <h1 className="text-[36px] font-semibold leading-[1.08] tracking-tight text-ink-900 md:text-display">
                    {c.lead}{" "}
                    <span className="text-accent">{c.accent}</span>
                  </h1>

                  <p className="max-w-md text-body leading-relaxed text-ink-600">{c.sub}</p>

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
                      href="#process"
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-ink-200 px-6 py-3.5 text-body font-medium text-ink-800 transition-colors hover:bg-ink-50"
                    >
                      See the process
                    </a>
                  </div>

                  <ul className="flex flex-wrap gap-x-5 gap-y-2">
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
                </motion.div>
              </AnimatePresence>
            </StaggerItem>
          </Stagger>

          <FadeUp delay={0.15} className="md:pl-2">
            <ChatPreviewLazy audience={audience} />
          </FadeUp>
        </div>
      </div>
    </section>
  );
}
