"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  Brain,
  Briefcase,
  FileText,
  GraduationCap,
  MessageSquare,
  Search,
  Send,
  ShieldCheck,
  Users,
} from "@/components/brand/icons";
import { SectionHeader } from "@/components/landing/SectionHeader";
import type { LandingAudience } from "@/components/landing/landing-audience";
import { RevealStagger, StaggerItem } from "@/components/ui/motion";

type Feature = { Icon: LucideIcon; title: string; body: string };

const CANDIDATE_FEATURES: Feature[] = [
  {
    Icon: MessageSquare,
    title: "One chat with Aarya",
    body: "No forms, no tabs. Aarya already read your CV and knows your market.",
  },
  {
    Icon: Briefcase,
    title: "Real roles, scored",
    body: "Aarya finds live openings in your region — ranked by fit, not keyword spam.",
  },
  {
    Icon: Send,
    title: "Warm intros",
    body: "Aarya hands you to the hiring manager with context. Not another ATS black hole.",
  },
  {
    Icon: FileText,
    title: "Tailored CVs",
    body: "Aarya builds a role-ready résumé in one click — highlights the right experience.",
  },
  {
    Icon: GraduationCap,
    title: "Skill roadmaps",
    body: "Gap between you and a role? Aarya builds an hour-a-day learning plan.",
  },
  {
    Icon: Brain,
    title: "Career intelligence",
    body: "Aarya shows your market value and next move — tied to actual openings.",
  },
];

const RECRUITER_FEATURES: Feature[] = [
  {
    Icon: MessageSquare,
    title: "One chat with Nitya",
    body: "Describe roles in plain words. Nitya builds the brief — no intake forms.",
  },
  {
    Icon: Search,
    title: "Smart shortlists",
    body: "Nitya searches the candidate graph and ranks matches by genuine fit.",
  },
  {
    Icon: Users,
    title: "Opted-in candidates",
    body: "Only people who want to be contacted appear in your pipeline.",
  },
  {
    Icon: Send,
    title: "Warm intros",
    body: "Nitya coordinates handoffs so you start warm conversations, not cold DMs.",
  },
  {
    Icon: ShieldCheck,
    title: "Consent-first",
    body: "Profiles are shared only with candidate permission. No spam, ever.",
  },
  {
    Icon: Brain,
    title: "Hiring intelligence",
    body: "Nitya logs every search and outreach — full transparency on every action.",
  },
];

const SECTION_COPY: Record<
  LandingAudience,
  { label: string; title: string; description: string }
> = {
  candidate: {
    label: "What Aarya does",
    title: "Your recruiter, coach, and strategist.",
    description: "Everything a great recruiter does for candidates — automated by Aarya.",
  },
  recruiter: {
    label: "What Nitya does",
    title: "Your sourcer, screener, and intro partner.",
    description: "Everything a great sourcer does for hiring teams — automated by Nitya.",
  },
};

type FeaturesSectionProps = {
  audience: LandingAudience;
};

export function FeaturesSection({ audience }: FeaturesSectionProps) {
  const features = audience === "candidate" ? CANDIDATE_FEATURES : RECRUITER_FEATURES;
  const header = SECTION_COPY[audience];

  return (
    <section id="features" className="scroll-mt-20 border-t border-ink-100 bg-paper-1">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <SectionHeader
          label={header.label}
          title={header.title}
          description={header.description}
        />

        <RevealStagger key={audience} className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ Icon, title, body }) => (
            <StaggerItem key={title}>
              <motion.div
                className="group h-full space-y-3 rounded-xl border border-ink-100 bg-paper-0 p-6"
                whileHover={{ y: -4, borderColor: "rgba(185,248,76,0.35)" }}
                transition={{ type: "spring", stiffness: 380, damping: 26 }}
              >
                <motion.span
                  className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-accent"
                  whileHover={{ scale: 1.08, rotate: -3 }}
                  transition={{ type: "spring", stiffness: 400, damping: 20 }}
                >
                  <Icon className="h-5 w-5" strokeWidth={1.5} />
                </motion.span>
                <h3 className="text-h3 text-ink-900">{title}</h3>
                <p className="text-small leading-relaxed text-ink-600">{body}</p>
              </motion.div>
            </StaggerItem>
          ))}
        </RevealStagger>
      </div>
    </section>
  );
}
