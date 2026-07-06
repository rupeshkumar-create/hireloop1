"use client";

import { useState } from "react";
import { LandingNav } from "@/components/landing/LandingNav";
import { HeroSection } from "@/components/landing/HeroSection";
import { CredibilityBar, ProcessSection } from "@/components/landing/ProcessSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import type { LandingAudience } from "@/components/landing/landing-audience";
import {
  CandidatesCrossSell,
  FinalCtaSection,
  LandingFooter,
  RecruitersSection,
  TrustSection,
} from "@/components/landing/TrustSection";

/**
 * Full landing page — audience state drives Aarya (candidate) vs Nitya (recruiter)
 * copy, chat demo, process, and features throughout.
 */
export function LandingPage() {
  const [audience, setAudience] = useState<LandingAudience>("candidate");

  return (
    <main className="min-h-screen bg-paper-0">
      <LandingNav />
      <HeroSection audience={audience} onAudienceChange={setAudience} />
      <CredibilityBar audience={audience} />
      <ProcessSection audience={audience} />
      <FeaturesSection audience={audience} />
      <TrustSection audience={audience} />
      {audience === "candidate" ? (
        <RecruitersSection />
      ) : (
        <CandidatesCrossSell onSwitch={() => setAudience("candidate")} />
      )}
      <FinalCtaSection audience={audience} />
      <LandingFooter />
    </main>
  );
}
