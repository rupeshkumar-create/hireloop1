"use client";

import { useState } from "react";
import { LandingNav } from "@/components/landing/LandingNav";
import { HeroSection } from "@/components/landing/HeroSection";
import type { LandingAudience } from "@/components/landing/landing-audience";
import {
  FinalCtaSection,
  LandingFooter,
  TrustSection,
} from "@/components/landing/TrustSection";

/**
 * Landing — type-led, fewer sections: hero → trust → CTA → footer.
 */
export function LandingPage() {
  const [audience, setAudience] = useState<LandingAudience>("candidate");

  return (
    <main className="min-h-screen bg-paper-0">
      <LandingNav />
      <HeroSection audience={audience} onAudienceChange={setAudience} />
      <TrustSection audience={audience} />
      <FinalCtaSection audience={audience} />
      <LandingFooter />
    </main>
  );
}
