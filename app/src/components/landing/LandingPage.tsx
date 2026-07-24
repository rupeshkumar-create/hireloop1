"use client";

import { useState } from "react";
import { LandingNav } from "@/components/landing/LandingNav";
import { HeroSection } from "@/components/landing/HeroSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import type { LandingAudience } from "@/components/landing/landing-audience";
import {
  CredibilityBar,
  ProcessSection,
} from "@/components/landing/ProcessSection";
import {
  FinalCtaSection,
  LandingFooter,
  TrustSection,
} from "@/components/landing/TrustSection";

/**
 * Landing — one audience choice drives one clear, complete product story.
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
      <FinalCtaSection audience={audience} />
      <LandingFooter />
    </main>
  );
}
