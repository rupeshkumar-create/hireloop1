import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";

export const metadata: Metadata = {
  title: "How It Works",
  description:
    "Step-by-step: how Aarya and Nitya work together to match candidates to jobs and make warm introductions to hiring managers.",
};

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://hireschema.com";

const CANDIDATE_STEPS = [
  { n: 1, title: "Sign in with LinkedIn", detail: "One click. Aarya reads your profile, work history, skills and education. No manual form filling." },
  { n: 2, title: "Set your home market", detail: "Pick where you want to work (12 supported countries). Optional phone verification via SMS for India (+91 MSG91). Resume upload sets your profile — no manual forms." },
  { n: 3, title: "Chat with Aarya", detail: "Tell her what you're looking for — role, company type, city, CTC. She builds your preference graph in real time." },
  { n: 4, title: "Review your match feed", detail: "Aarya surfaces the top 10 roles daily, ranked by semantic match score. Each card shows role, company, CTC, and your fit score." },
  { n: 5, title: "Pick an action on each role", detail: "Three options: Direct Apply (via the job's native link), Request Intro (warm intro via your Gmail), or Save for Later." },
  { n: 6, title: "Approve the intro email", detail: "For Request Intro, Nitya drafts a personalised email from your Gmail. You approve or edit — then it's sent." },
  { n: 7, title: "Track replies & prep for interviews", detail: "See real-time status. When a hiring manager replies, Aarya automatically starts interview prep for that role." },
];

const RECRUITER_STEPS = [
  { n: 1, title: "Describe the role", detail: "Plain English is fine. Nitya asks follow-up questions if she needs more signal — seniority, must-haves, company culture." },
  { n: 2, title: "Nitya builds the brief", detail: "She generates a structured hiring brief and converts it into a semantic search query across the candidate graph." },
  { n: 3, title: "Review the shortlist", detail: "Ranked candidates with match score cards. Filter by skill fit, experience, CTC alignment, or availability." },
  { n: 4, title: "Nitya enriches contacts", detail: "For each candidate you want to reach, Nitya runs the Apify waterfall: LinkedIn → email finder → NeverBounce verify." },
  { n: 5, title: "Intros go out via candidate Gmail", detail: "The email comes from the candidate's own Gmail — not a recruiter address. Reply rates are 3× higher." },
  { n: 6, title: "Manage the pipeline", detail: "Track every intro, every reply, every stage in the Nitya pipeline view. Auto-reminders for follow-ups." },
];

const ARCHITECTURE = [
  { icon: "🧠", label: "Conversational Engine", desc: "Claude-3.5-Sonnet via OpenRouter. Single-threaded master agent loop. All state persisted in Postgres via LangGraph." },
  { icon: "📚", label: "Knowledge Engine", desc: "pgvector HNSW indexes on candidate and job embeddings. Semantic cosine similarity — not keyword matching." },
  { icon: "🔗", label: "Matching Engine", desc: "Multi-signal scoring: skills (40%), experience (25%), location (20%), CTC (15%). Bias audit on every score." },
  { icon: "🔁", label: "Intro Handshake", desc: "DB-state driven. Candidate clicks → intro_requests table INSERT → Postgres NOTIFY wakes Nitya → Gmail OAuth send." },
];

export default function HowItWorksPage() {
  return (
    <main>
      <section className="border-b border-ink-100 bg-paper-0">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <Badge variant="brand" className="mb-4 bg-ink-700/60 text-paper-0 border-ink-700">
            Under the hood
          </Badge>
          <h1 className="text-5xl font-bold text-paper-0 mb-4">How Hireschema works</h1>
          <p className="text-ink-300 text-lg">
            Two AI agents. One shared candidate graph. End-to-end — from profile to offer.
          </p>
        </div>
      </section>

      {/* Candidate flow */}
      <section className="py-20 bg-paper-1">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="flex items-center gap-3 mb-10">
            <div className="w-10 h-10 rounded-full ">A</div>
            <h2 className="text-3xl font-bold text-ink-900">Aarya — Candidate flow</h2>
          </div>
          <div className="space-y-4">
            {CANDIDATE_STEPS.map((s) => (
              <div key={s.n} className="flex gap-5 bg-ink-50 rounded-2xl p-5">
                <div className="w-8 h-8 rounded-full bg-ink-50 text-accent font-bold text-sm flex items-center justify-center shrink-0 mt-0.5">
                  {s.n}
                </div>
                <div>
                  <p className="font-semibold text-ink-900">{s.title}</p>
                  <p className="text-sm text-ink-500 mt-1">{s.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Recruiter flow */}
      <section className="py-20 bg-ink-50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="flex items-center gap-3 mb-10">
            <div className="w-10 h-10 rounded-full ">N</div>
            <h2 className="text-3xl font-bold text-ink-900">Nitya — Recruiter flow</h2>
          </div>
          <div className="space-y-4">
            {RECRUITER_STEPS.map((s) => (
              <div key={s.n} className="flex gap-5 bg-paper-1 rounded-2xl p-5 shadow-sm border border-ink-100">
                <div className="w-8 h-8 rounded-full bg-accent text-accent font-bold text-sm flex items-center justify-center shrink-0 mt-0.5">
                  {s.n}
                </div>
                <div>
                  <p className="font-semibold text-ink-900">{s.title}</p>
                  <p className="text-sm text-ink-500 mt-1">{s.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section className="py-20 bg-ink-900">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-paper-0 mb-3">Three-engine architecture</h2>
            <p className="text-ink-500">Inspired by the Jack & Jill model — built for India.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {ARCHITECTURE.map((a) => (
              <div key={a.label} className="bg-ink-900 rounded-2xl p-5 border border-ink-700">
                <span className="text-2xl block mb-3">{a.icon}</span>
                <p className="text-paper-0 font-semibold text-sm mb-2">{a.label}</p>
                <p className="text-ink-500 text-xs leading-relaxed">{a.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 bg-paper-1 text-center">
        <div className="max-w-lg mx-auto px-4">
          <h2 className="text-3xl font-bold text-ink-900 mb-4">Ready to try it?</h2>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href={APP_URL + "/signup?role=candidate"}
              className="inline-flex items-center justify-center bg-accent hover:bg-accent-hover text-paper-0 font-semibold px-6 py-3 rounded-xl text-sm transition-colors"
            >
              I&apos;m a job seeker →
            </Link>
            <Link
              href={APP_URL + "/signup?role=recruiter"}
              className="inline-flex items-center justify-center border border-ink-100 hover:bg-ink-50 text-ink-700 font-semibold px-6 py-3 rounded-xl text-sm transition-colors"
            >
              I&apos;m hiring →
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
