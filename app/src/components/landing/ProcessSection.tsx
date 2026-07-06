"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  Briefcase,
  FileText,
  MapPin,
  MessageSquare,
  Mic,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "@/components/brand/icons";
import { SectionHeader } from "@/components/landing/SectionHeader";
import {
  LANDING_AGENTS,
  type LandingAudience,
} from "@/components/landing/landing-audience";
import { RevealStagger, StaggerItem } from "@/components/ui/motion";

type Step = {
  step: string;
  Icon: LucideIcon;
  title: string;
  body: string;
  detail: string;
};

const CANDIDATE_STEPS: Step[] = [
  {
    step: "01",
    Icon: MessageSquare,
    title: "Tell Aarya what you want",
    body: "Upload your CV or paste your LinkedIn. Say the role, city, and pay band — type it or talk. Aarya builds your profile from the conversation.",
    detail: "Aarya · voice or text",
  },
  {
    step: "02",
    Icon: Search,
    title: "Aarya hunts in your region",
    body: "Live openings near you first — your city, then your country, then remote roles you qualify for. Currency and market adjust automatically.",
    detail: "Vienna → Austria → EU remote",
  },
  {
    step: "03",
    Icon: Briefcase,
    title: "Aarya scores every role",
    body: "Real jobs, ranked by genuine match — skills, seniority, location, and comp. You see why each role fits and what to improve.",
    detail: "Transparent scoring · Skill gaps",
  },
  {
    step: "04",
    Icon: Send,
    title: "Aarya requests warm intros",
    body: "Pick a role you like. Aarya tailors your CV, drafts the outreach, and sends a warm intro from your Gmail — not a cold apply into the void.",
    detail: "CV per role · Consent-first",
  },
];

const RECRUITER_STEPS: Step[] = [
  {
    step: "01",
    Icon: MessageSquare,
    title: "Tell Nitya the role",
    body: "Describe the opening in plain words — title, skills, location, and comp. Nitya turns it into a structured brief without forms or templates.",
    detail: "Nitya · voice or text",
  },
  {
    step: "02",
    Icon: Search,
    title: "Nitya searches the graph",
    body: "Nitya scans pre-verified candidates in your market who match the brief — skills, seniority, location, and interest signals.",
    detail: "Live candidate graph",
  },
  {
    step: "03",
    Icon: Users,
    title: "Nitya ranks who opted in",
    body: "Only candidates who want to be contacted surface in your shortlist — ranked by fit score, not keyword spam.",
    detail: "Pre-scored · Consent-first",
  },
  {
    step: "04",
    Icon: Send,
    title: "Nitya warms up the intro",
    body: "Nitya drafts the outreach and coordinates a warm handoff — so you start conversations with interested people, not cold DMs.",
    detail: "Warm intros · No spam",
  },
];

const SECTION_COPY: Record<
  LandingAudience,
  { label: string; title: string; description: string }
> = {
  candidate: {
    label: "How Aarya works",
    title: "Four steps. One chat with Aarya.",
    description:
      "Aarya is your candidate agent — it runs the job search while you watch every move.",
  },
  recruiter: {
    label: "How Nitya works",
    title: "Four steps. One chat with Nitya.",
    description:
      "Nitya is your recruiter agent — it sources and shortlists while you stay in control.",
  },
};

type ProcessSectionProps = {
  audience: LandingAudience;
};

export function ProcessSection({ audience }: ProcessSectionProps) {
  const steps = audience === "candidate" ? CANDIDATE_STEPS : RECRUITER_STEPS;
  const header = SECTION_COPY[audience];
  const agent = LANDING_AGENTS[audience];

  return (
    <section id="process" className="scroll-mt-20 border-t border-ink-100 bg-paper-0">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <SectionHeader
          label={header.label}
          title={header.title}
          description={header.description}
        />

        <div className="relative mt-14">
          <div
            className="absolute left-[27px] top-8 hidden h-[calc(100%-4rem)] w-px bg-gradient-to-b from-accent/60 via-ink-200 to-transparent md:block"
            aria-hidden
          />

          <RevealStagger key={audience} className="space-y-6">
            {steps.map(({ step, Icon, title, body, detail }, i) => (
              <StaggerItem key={`${audience}-${step}`}>
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
                      <span className="text-micro text-ink-400">
                        {agent.name} · Step {step}
                      </span>
                    </div>
                    <p className="text-small leading-relaxed text-ink-600">{body}</p>
                    <p className="inline-flex items-center gap-1.5 text-micro font-medium text-accent">
                      <Sparkles className="h-3 w-3" strokeWidth={1.5} />
                      {detail}
                    </p>
                  </div>

                  {i < steps.length - 1 ? (
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

const CREDIBILITY: Record<
  LandingAudience,
  { Icon: LucideIcon; label: string; sub: string }[]
> = {
  candidate: [
    { Icon: Mic, label: "Talk to Aarya", sub: "Text or voice" },
    { Icon: MapPin, label: "Your region", sub: "City → country → remote" },
    { Icon: Zap, label: "Live actions", sub: "Every step logged" },
    { Icon: FileText, label: "CV per role", sub: "Aarya tailors each one" },
  ],
  recruiter: [
    { Icon: Mic, label: "Talk to Nitya", sub: "Text or voice" },
    { Icon: MapPin, label: "Your market", sub: "Local talent pools" },
    { Icon: Zap, label: "Live actions", sub: "Every step logged" },
    { Icon: ShieldCheck, label: "Consent-first", sub: "Opted-in candidates only" },
  ],
};

type CredibilityBarProps = {
  audience: LandingAudience;
};

export function CredibilityBar({ audience }: CredibilityBarProps) {
  const items = CREDIBILITY[audience];

  return (
    <section className="border-y border-ink-100 bg-paper-1">
      <RevealStagger key={audience} className="mx-auto grid max-w-page grid-cols-2 gap-6 px-6 py-8 md:grid-cols-4">
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
