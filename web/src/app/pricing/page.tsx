import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Hireloop is free for job seekers. Recruiters pay per successful outcome. No subscriptions during beta.",
};

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.hireloop.in";

type Plan = {
  name: string;
  price: string;
  period: string;
  tagline: string;
  features: string[];
  cta: string;
  href: string;
  highlight: boolean;
  note?: string;
};

const PLANS: Plan[] = [
  {
    name: "Candidate",
    price: "Free",
    period: "forever",
    tagline: "For job seekers",
    features: [
      "Aarya AI chat — unlimited",
      "Job match feed — daily refresh",
      "Request Intro — 5 per month (beta)",
      "Tailored resume PDF — 3 per month",
      "20-min career call with Aarya",
      "Mock interview prep",
      "WhatsApp + in-app notifications",
    ],
    cta: "Start chatting — it's free",
    href: APP_URL + "/signup?role=candidate",
    highlight: true,
  },
  {
    name: "Recruiter — Beta",
    price: "₹0",
    period: "during beta",
    tagline: "For hiring teams",
    features: [
      "Nitya AI recruiter — full access",
      "Semantic candidate search",
      "Shortlists with bias-audited score cards",
      "HM contact enrichment — ₹9–13/contact",
      "Warm intro pipeline tracking",
      "WhatsApp status updates",
      "Placement fee: manual invoice (beta)",
    ],
    cta: "Talk to Nitya — free",
    href: APP_URL + "/signup?role=recruiter",
    highlight: false,
    note: "Post-beta: % of first-year CTC per hire. India-market pricing.",
  },
];

export default function PricingPage() {
  return (
    <main>
      <section className="border-b border-ink-100">
        <div className="max-w-page mx-auto px-6 py-24 sm:py-28">
          <div className="max-w-2xl">
            <Badge variant="brand" className="mb-4">
              Simple pricing
            </Badge>
            <h1 className="text-display text-ink-900 mb-5 leading-[1.05]">
              Free for candidates.
              <span className="text-ink-500"> Fair for recruiters.</span>
            </h1>
            <p className="text-h3 text-ink-700 font-normal leading-relaxed">
              No subscriptions during beta. Candidates are always free.
            </p>
          </div>
        </div>
      </section>

      <section className="py-20">
        <div className="max-w-page mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-6">
            {PLANS.map((plan) => (
              <div
                key={plan.name}
                className={[
                  "rounded-xl border border-ink-100 bg-paper-1 p-8",
                  plan.highlight ? "shadow-ink-100/50 shadow-xl" : "",
                ].join(" ")}
              >
                {plan.highlight && (
                  <div className="mb-5">
                    <Badge variant="brand">Most popular</Badge>
                  </div>
                )}

                <p className="text-micro text-ink-500 uppercase mb-2">
                  {plan.tagline}
                </p>
                <h2 className="text-h2 text-ink-900 mb-2">{plan.name}</h2>
                <div className="flex items-baseline gap-2 mb-7">
                  <span className="text-4xl font-semibold text-ink-900">
                    {plan.price}
                  </span>
                  <span className="text-small text-ink-500">{plan.period}</span>
                </div>

                <ul className="space-y-3 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-3 text-small text-ink-700">
                      <svg
                        className="w-4 h-4 text-ink-900 mt-0.5 shrink-0"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2.5}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      {f}
                    </li>
                  ))}
                </ul>

                <Link
                  href={plan.href}
                  className={[
                    "block text-center font-medium px-5 h-12 rounded-md text-body transition-colors duration-fast",
                    plan.highlight
                      ? "bg-accent hover:bg-accent-hover text-accent-fg"
                      : "bg-ink-50 hover:bg-ink-100 text-ink-900",
                  ].join(" ")}
                >
                  {plan.cta}
                </Link>

                {plan.note && (
                  <p className="mt-4 text-small text-ink-500">{plan.note}</p>
                )}
              </div>
            ))}
          </div>

          <div className="mt-12 bg-ink-50 rounded-xl p-6">
            <p className="text-small text-ink-700">
              India only · All prices in INR · DPDP Act 2023 compliant ·{" "}
              <a href="mailto:hello@hireloop.in" className="text-accent underline">
                Questions? hello@hireloop.in
              </a>
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
