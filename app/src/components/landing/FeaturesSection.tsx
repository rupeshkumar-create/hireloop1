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
    body: "Ask for roles, compare matches, and prepare applications without learning a complicated workflow.",
  },
  {
    Icon: Briefcase,
    title: "Real roles, scored",
    body: "Aarya finds live openings in your region — ranked by fit, not keyword spam.",
  },
  {
    Icon: Send,
    title: "Warm intros",
    body: "Review the draft, connect Gmail, and approve the message before Aarya sends it.",
  },
  {
    Icon: FileText,
    title: "Tailored CVs",
    body: "Prepare a role-specific résumé that stays grounded in your real experience.",
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
    body: "Describe the role in plain words. Nitya turns it into a brief you can review and edit.",
  },
  {
    Icon: Search,
    title: "Smart shortlists",
    body: "Nitya ranks candidates against the active role and shows the evidence behind the score.",
  },
  {
    Icon: Users,
    title: "Opted-in candidates",
    body: "Only people who want to be contacted appear in your pipeline.",
  },
  {
    Icon: Send,
    title: "Warm intros",
    body: "Request a two-sided introduction and let the candidate accept or decline.",
  },
  {
    Icon: ShieldCheck,
    title: "Consent-first",
    body: "Recruiter search includes only candidates who turned discovery on.",
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
    description:
      "Search, matching, application preparation, and career guidance — with you in control.",
  },
  recruiter: {
    label: "What Nitya does",
    title: "Your sourcer, screener, and intro partner.",
    description:
      "Role intake, matching, evidence, and introductions — scoped to the role you are hiring for.",
  },
};

type FeaturesSectionProps = {
  audience: LandingAudience;
};

export function FeaturesSection({ audience }: FeaturesSectionProps) {
  const features =
    audience === "candidate" ? CANDIDATE_FEATURES : RECRUITER_FEATURES;
  const header = SECTION_COPY[audience];

  return (
    <section
      id="features"
      className="scroll-mt-20 border-t border-ink-100 bg-paper-1"
    >
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <SectionHeader
          label={header.label}
          title={header.title}
          description={header.description}
        />

        <RevealStagger
          key={audience}
          className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
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
                <p className="text-small leading-relaxed text-ink-600">
                  {body}
                </p>
              </motion.div>
            </StaggerItem>
          ))}
        </RevealStagger>
      </div>
    </section>
  );
}
