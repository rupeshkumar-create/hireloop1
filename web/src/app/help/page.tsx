import type { Metadata } from "next";
import Link from "next/link";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.hireloop.in";

export const metadata: Metadata = {
  title: "Help & support",
  description: "Get help with Hireloop — candidates, recruiters, privacy, and account issues.",
};

const FAQ = [
  {
    q: "How do I sign up as a candidate?",
    a: "Go to the app, sign in with LinkedIn, verify your +91 number, and Aarya will show your matches on the dashboard.",
  },
  {
    q: "Where are my job matches?",
    a: "Open Matches on the left panel of your dashboard — chat with Aarya on the right for questions and intros.",
  },
  {
    q: "How do intro requests work?",
    a: "Request an intro from a job card. Aarya drafts a warm email; you send it from your own Gmail after approving the draft.",
  },
  {
    q: "I'm a recruiter — how do I claim an invite?",
    a: "Open the link in your email, accept the invite, and the candidate appears in your recruiter inbox.",
  },
  {
    q: "How do I delete my data?",
    a: "In the app, go to Settings → Privacy → request export or deletion. You can also email privacy@hireloop.in.",
  },
];

export default function HelpPage() {
  return (
    <main className="bg-paper-1 min-h-screen py-16">
      <div className="max-w-2xl mx-auto px-4 sm:px-6">
        <h1 className="text-h1 font-semibold text-ink-900">Help & support</h1>
        <p className="mt-2 text-body text-ink-600">
          Quick answers for candidates and recruiters using Hireloop in India.
        </p>

        <div className="mt-10 space-y-6">
          {FAQ.map((item) => (
            <div key={item.q} className="rounded-lg border border-ink-100 bg-paper-0 p-5">
              <h2 className="text-body font-semibold text-ink-900">{item.q}</h2>
              <p className="mt-2 text-small text-ink-600 leading-relaxed">{item.a}</p>
            </div>
          ))}
        </div>

        <div className="mt-12 rounded-lg border border-ink-100 bg-ink-50 p-6 space-y-3">
          <p className="text-body font-medium text-ink-900">Still stuck?</p>
          <p className="text-small text-ink-600">
            Email{" "}
            <a href="mailto:privacy@hireloop.in" className="underline text-ink-900">
              privacy@hireloop.in
            </a>{" "}
            for privacy or account issues, or{" "}
            <a href="mailto:hello@hireloop.in" className="underline text-ink-900">
              hello@hireloop.in
            </a>{" "}
            for general support.
          </p>
          <Link
            href={`${APP_URL}/dashboard`}
            className="inline-flex text-small font-medium text-accent hover:text-accent-hover"
          >
            Open the app →
          </Link>
        </div>
      </div>
    </main>
  );
}
