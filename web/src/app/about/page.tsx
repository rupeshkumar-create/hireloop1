import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About Hireschema",
  description:
    "Hireschema is an AI recruiting platform — inspired by Jack & Jill (London) but built for India, the US, and the UK with local compliance and market-aware matching.",
};

const VALUES = [
  {
    icon: "🇮🇳",
    title: "Market-first",
    desc: "Each candidate has a home market (IN / US / GB). Jobs, salaries, and phone verification are scoped to that region — not a one-size-fits-all US product retrofitted.",
  },
  {
    icon: "🤝",
    title: "Warm > cold",
    desc: "A hiring manager who receives an email from the candidate directly — not a recruiter blast — is 3× more likely to reply. We built the platform around that insight.",
  },
  {
    icon: "🔒",
    title: "Privacy by design",
    desc: "DPDP Act 2023 compliance is not a checkbox. Consent logs, data export, right-to-delete, and bias audits are baked into the core schema — not bolted on.",
  },
  {
    icon: "⚡",
    title: "AI with guardrails",
    desc: "Aarya and Nitya are powerful, but they never send an email without your approval. The human is always in the loop for consequential actions.",
  },
];

export default function AboutPage() {
  return (
    <main>
      {/* Hero */}
      <section className="border-b border-ink-100 bg-paper-0">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h1 className="text-5xl font-bold text-paper-0 mb-6">
            We&apos;re building the career layer for India
          </h1>
          <p className="text-ink-300 text-lg leading-relaxed">
            Inspired by what Jack & Jill built in London — but designed from the ground up
            for the Indian job market, Indian talent, and Indian compliance.
          </p>
        </div>
      </section>

      {/* Story */}
      <section className="py-20 bg-paper-1">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 prose prose-gray">
          <h2 className="text-3xl font-bold text-ink-900 mb-6">The story</h2>
          <p className="text-ink-700 leading-relaxed mb-4">
            In 2025, Tinker Tailor Talent (Jack & Jill) raised $20M seed to build an AI
            recruiting platform in London — two AI agents (one for candidates, one for
            recruiters) sharing a single candidate graph. They used a &ldquo;warm intro&rdquo;
            mechanic where emails come from the candidate&apos;s own inbox, not a recruiter blast.
            Reply rates 3× industry average.
          </p>
          <p className="text-ink-700 leading-relaxed mb-4">
            India has 500M workers and no equivalent. The job boards are noisy. LinkedIn InMail
            is expensive and cold. Placement agencies charge 8–12% with zero transparency.
          </p>
          <p className="text-ink-700 leading-relaxed">
            Hireschema is the Indian version — built with the same three-engine architecture
            (conversational → knowledge → matching), adapted for Indian compliance (DPDP Act 2023),
            Indian infrastructure (ap-south-1), and Indian cost structures (₹9–13/enriched contact,
            not $40 Apollo credits).
          </p>
        </div>
      </section>

      {/* Values */}
      <section className="py-20 bg-ink-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <h2 className="text-3xl font-bold text-ink-900 mb-10 text-center">What we stand for</h2>
          <div className="grid sm:grid-cols-2 gap-6">
            {VALUES.map((v) => (
              <div key={v.title} className="bg-paper-1 rounded-2xl p-6 border border-ink-100">
                <span className="text-3xl block mb-3">{v.icon}</span>
                <h3 className="font-bold text-ink-900 mb-2">{v.title}</h3>
                <p className="text-sm text-ink-500 leading-relaxed">{v.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Contact */}
      <section className="py-20 bg-paper-1 text-center">
        <div className="max-w-xl mx-auto px-4">
          <h2 className="text-2xl font-bold text-ink-900 mb-4">Get in touch</h2>
          <p className="text-ink-500 mb-6">
            Founders, investors, early customers — we&apos;d love to hear from you.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <a
              href="mailto:hello@hireschema.com"
              className="inline-flex items-center justify-center bg-accent hover:bg-accent-hover text-paper-0 font-semibold px-6 py-3 rounded-xl text-sm transition-colors"
            >
              hello@hireschema.com
            </a>
            <Link
              href="/contact"
              className="inline-flex items-center justify-center border border-ink-100 hover:bg-ink-50 text-ink-700 font-semibold px-6 py-3 rounded-xl text-sm transition-colors"
            >
              Contact form →
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
