"use client";

import { motion } from "framer-motion";
import {
  Brain,
  Briefcase,
  FileText,
  GraduationCap,
  MessageSquare,
  Send,
} from "@/components/brand/icons";
import { RevealStagger, StaggerItem } from "@/components/ui/motion";
import { SectionHeader } from "@/components/landing/SectionHeader";

const FEATURES = [
  {
    Icon: MessageSquare,
    title: "One chat surface",
    body: "No forms, no tabs. Talk to Aarya like a recruiter who already read your CV.",
  },
  {
    Icon: Briefcase,
    title: "Real roles, scored",
    body: "Live openings from your market — ranked by fit, not keyword spam.",
  },
  {
    Icon: Send,
    title: "Warm intros",
    body: "Handed to the hiring manager with context. Not another ATS black hole.",
  },
  {
    Icon: FileText,
    title: "Tailored CVs",
    body: "One click to a role-ready résumé that highlights the right experience.",
  },
  {
    Icon: GraduationCap,
    title: "Skill roadmaps",
    body: "Gap between you and the role? Aarya builds an hour-a-day learning plan.",
  },
  {
    Icon: Brain,
    title: "Career intelligence",
    body: "Know your market value and next move — tied to actual openings.",
  },
] as const;

export function FeaturesSection() {
  return (
    <section id="features" className="scroll-mt-20 border-t border-ink-100 bg-paper-1">
      <div className="mx-auto max-w-page px-6 py-16 md:py-24">
        <SectionHeader
          label="What you get"
          title="A recruiter, coach, and strategist — in one thread."
          description="Everything a good recruiter does for you, automated and transparent."
        />

        <RevealStagger className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ Icon, title, body }) => (
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
