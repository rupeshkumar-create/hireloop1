"use client";

import { motion } from "framer-motion";
import {
  Briefcase,
  FileText,
  MapPin,
  MessageSquare,
  Mic,
  Search,
  Send,
  Sparkles,
  Zap,
} from "@/components/brand/icons";
import { RevealStagger, StaggerItem } from "@/components/ui/motion";
import { SectionHeader } from "@/components/landing/SectionHeader";

const STEPS = [
  {
    step: "01",
    Icon: MessageSquare,
    title: "Tell Aarya what you want",
    body: "Upload your CV or paste your LinkedIn. Say the role, city, and pay band — type it or talk. Aarya builds your profile from the conversation.",
    detail: "Voice or text · Any format CV",
  },
  {
    step: "02",
    Icon: Search,
    title: "It hunts in your region",
    body: "Live openings near you first — your city, then your country, then remote roles you qualify for. Currency and market adjust automatically.",
    detail: "Vienna → Austria → EU remote",
  },
  {
    step: "03",
    Icon: Briefcase,
    title: "Every role gets a fit score",
    body: "Real jobs, ranked by genuine match — skills, seniority, location, and comp. No black box: you see why each role fits and what to improve.",
    detail: "Transparent scoring · Skill gaps",
  },
  {
    step: "04",
    Icon: Send,
    title: "Request a warm intro",
    body: "Pick a role you like. Aarya tailors your CV, drafts the outreach, and sends a warm intro from your Gmail — not a cold apply into the void.",
    detail: "CV per role · Consent-first",
  },
] as const;

export function ProcessSection() {
  return (
    <section id="process" className="scroll-mt-20 border-t border-ink-100 bg-paper-0">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <SectionHeader
          label="The process"
          title="Four steps. One conversation."
          description="Hireschema isn't another job board — it's an AI agent that runs your search while you watch every move."
        />

        <div className="relative mt-14">
          {/* Connecting line (desktop) */}
          <div
            className="absolute left-[27px] top-8 hidden h-[calc(100%-4rem)] w-px bg-gradient-to-b from-accent/60 via-ink-200 to-transparent md:block"
            aria-hidden
          />

          <RevealStagger className="space-y-6">
            {STEPS.map(({ step, Icon, title, body, detail }, i) => (
              <StaggerItem key={step}>
                <motion.article
                  className="group relative grid gap-4 rounded-xl border border-ink-100 bg-paper-1 p-6 transition-colors hover:border-ink-300 md:grid-cols-[auto_1fr] md:gap-6"
                  whileHover={{ y: -2 }}
                  transition={{ type: "spring", stiffness: 400, damping: 28 }}
                >
                  <div className="flex items-start gap-4 md:flex-col md:items-center md:gap-3">
                    <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-ink-900 ring-2 ring-accent/20">
                      <Icon className="h-6 w-6 text-paper-0" strokeWidth={1.5} />
                      <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded bg-accent text-[10px] font-bold text-on-accent">
                        {step.replace("0", "")}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-h3 text-ink-900">{title}</h3>
                      <span className="text-micro text-ink-400">Step {step}</span>
                    </div>
                    <p className="text-small leading-relaxed text-ink-600">{body}</p>
                    <p className="inline-flex items-center gap-1.5 text-micro font-medium text-accent">
                      <Sparkles className="h-3 w-3" strokeWidth={1.5} />
                      {detail}
                    </p>
                  </div>

                  {i < STEPS.length - 1 ? (
                    <motion.div
                      className="absolute -bottom-3 left-7 hidden h-6 w-6 items-center justify-center rounded-full bg-paper-0 ring-1 ring-ink-100 md:flex"
                      initial={{ scale: 0 }}
                      whileInView={{ scale: 1 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.2 + i * 0.1, type: "spring" }}
                      aria-hidden
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                    </motion.div>
                  ) : null}
                </motion.article>
              </StaggerItem>
            ))}
          </RevealStagger>
        </div>
      </div>
    </section>
  );
}

export function CredibilityBar() {
  const items = [
    { Icon: Mic, label: "Text or voice", sub: "Same AI pipeline" },
    { Icon: MapPin, label: "Global markets", sub: "IN · US · UK · EU+" },
    { Icon: Zap, label: "Live actions", sub: "Every step logged" },
    { Icon: FileText, label: "CV per role", sub: "One-click tailoring" },
  ] as const;

  return (
    <section className="border-y border-ink-100 bg-paper-1">
      <RevealStagger className="mx-auto grid max-w-page grid-cols-2 gap-6 px-6 py-8 md:grid-cols-4">
        {items.map(({ Icon, label, sub }) => (
          <StaggerItem key={label}>
            <motion.div
              className="flex items-start gap-3"
              whileHover={{ x: 2 }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10">
                <Icon className="h-4 w-4 text-accent" strokeWidth={1.5} />
              </span>
              <div>
                <p className="text-small font-semibold text-ink-900">{label}</p>
                <p className="text-micro text-ink-500">{sub}</p>
              </div>
            </motion.div>
          </StaggerItem>
        ))}
      </RevealStagger>
    </section>
  );
}
