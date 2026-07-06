"use client";

import { LandingNav } from "@/components/landing/LandingNav";
import { HeroSection } from "@/components/landing/HeroSection";
import { CredibilityBar, ProcessSection } from "@/components/landing/ProcessSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import {
  FinalCtaSection,
  LandingFooter,
  RecruitersSection,
  TrustSection,
} from "@/components/landing/TrustSection";

/**
 * Full landing page — client shell so Framer Motion can run on every section.
 */
export function LandingPage() {
  return (
    <main className="min-h-screen bg-paper-0">
      <LandingNav />
      <HeroSection />
      <CredibilityBar />
      <ProcessSection />
      <FeaturesSection />
      <TrustSection />
      <RecruitersSection />
      <FinalCtaSection />
      <LandingFooter />
    </main>
  );
}
