import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "Hireschema Privacy Policy — DPDP Act 2023 compliant. How we collect, use, and protect your personal data.",
  robots: { index: true, follow: true },
};

const SECTIONS = [
  {
    id: "overview",
    title: "1. Overview",
    content: `Hireschema ("Hireschema", "we", "us") operates an AI-powered recruiting platform for candidates and recruiters in India (+91 phone collection; SMS OTP verification when enabled). This Privacy Policy explains how we collect, use, store, and protect your personal data in compliance with India's Digital Personal Data Protection (DPDP) Act 2023.

By using Hireschema, you consent to the practices described in this policy. If you do not agree, please do not use the platform.`,
  },
  {
    id: "data-collected",
    title: "2. Data we collect",
    content: `Professional profile data: Name, email, phone (market dial code verified), work history, skills, education, and salary expectations — collected via LinkedIn OAuth or manual entry.

Resume and documents: Files you upload (PDF/DOCX). Stored securely in Supabase Storage (AWS ap-south-1) with signed URL access only.

Conversation data: Chat messages and voice transcripts from your interactions with Aarya. Retained for 90 days.

Usage data: Pages visited, features used, session timestamps. Used for product improvement only. Not sold.

LinkedIn OAuth data: Public profile fields authorised by you at sign-in. We store only what is displayed in your public LinkedIn profile.

Google OAuth data: We store OAuth tokens to send intro emails on your behalf and to create calendar events for voice-session bookings you request. We never read your inbox or existing calendar contents. Scopes: gmail.send and calendar.events only.`,
  },
  {
    id: "purpose",
    title: "3. Purpose of processing",
    content: `We process your data for the following purposes (DPDP Act §6):

• Profile creation and job matching (core service)
• Sending warm intro emails to hiring managers (with your explicit approval)
• Sending transactional notifications (job matches, intro status, interview reminders)
• Platform security, fraud prevention, and abuse detection
• Product analytics and improvement (anonymised)
• Legal compliance and dispute resolution

Every data collection event is logged in our consent_log table with purpose, timestamp, and your IP address.`,
  },
  {
    id: "sharing",
    title: "4. Data sharing",
    content: `We do not sell your personal data. We share data only in the following cases:

• With hiring managers (name, headline, skills summary — when you request an intro)
• With our technical vendors (Supabase, OpenRouter, Deepgram, Apify, SendGrid, MSG91) solely to provide the service — all are contractually bound by data processing agreements
• When required by Indian law or a court order
• In aggregate, anonymised form for research or product improvement

We do not share data with advertisers, data brokers, or third-party marketers.`,
  },
  {
    id: "storage",
    title: "5. Data storage and security",
    content: `All data is stored in AWS ap-south-1 (Mumbai, India). We do not transfer personal data outside India except to our technical sub-processors (listed in our DPA, available on request).

Security measures: TLS 1.3 in transit, AES-256 at rest, Row Level Security on all Postgres tables, signed-URL-only file access, no plain-text secrets in code.`,
  },
  {
    id: "retention",
    title: "6. Retention and deletion",
    content: `Active accounts: We retain your data while your account is active and for 30 days after deletion (to handle disputes).

Soft delete: When you delete your account, your data is marked deleted_at and purged from our databases after 30 days via automated pg_cron job.

Conversation history: Chat and voice transcripts are deleted after 90 days.

Right to deletion: You can request immediate deletion by emailing privacy@hireschema.com or using the in-app "Delete my account" button.`,
  },
  {
    id: "rights",
    title: "7. Your rights under DPDP Act 2023",
    content: `Under the DPDP Act 2023, you have the right to:

• Access: Request a copy of all personal data we hold about you.
• Correction: Request correction of inaccurate data.
• Erasure: Request deletion of your data (see §6).
• Nomination: Nominate a person to exercise your rights on your behalf.
• Grievance redressal: Lodge a complaint with our DPO (below).

To exercise these rights: Email privacy@hireschema.com or use the in-app "Data & Privacy" settings. We respond within 72 hours.`,
  },
  {
    id: "cookies",
    title: "8. Cookies",
    content: `We use essential cookies only: session tokens for authentication (via Supabase Auth) and CSRF protection tokens. We do not use advertising, tracking, or analytics cookies from third parties.`,
  },
  {
    id: "children",
    title: "9. Children's data",
    content: `Hireschema is not available to persons under 18. We do not knowingly collect data from minors. If you believe a minor has created an account, contact privacy@hireschema.com immediately.`,
  },
  {
    id: "dpo",
    title: "10. Data Protection Officer (DPO)",
    content: `Hireschema has designated a Data Protection Officer as required under DPDP Act 2023.

DPO Contact: privacy@hireschema.com
Response time: 72 hours for privacy-related requests, 30 days for formal DPDP Act requests.`,
  },
  {
    id: "updates",
    title: "11. Updates to this policy",
    content: `We may update this policy. Material changes will be notified by email and in-app at least 7 days before they take effect. Continued use after the effective date constitutes acceptance.

Last updated: July 2026`,
  },
];

export default function PrivacyPage() {
  return (
    <main id="main-content" className="py-16 bg-paper-1 min-h-screen">
      <div className="max-w-3xl mx-auto px-4 sm:px-6">
        <div className="mb-10">
          <div className="inline-flex items-center gap-2 bg-ink-50 text-ink-900 text-xs font-medium px-3 py-1 rounded-full mb-4">
            DPDP Act 2023 compliant
          </div>
          <h1 className="text-4xl font-bold text-ink-900 mb-2">Privacy Policy</h1>
          <p className="text-ink-500 text-sm">Effective: July 2026 · India</p>
        </div>

        <nav className="bg-ink-50 rounded-2xl p-5 mb-10" aria-label="Table of contents">
          <p className="text-xs font-semibold text-ink-500 uppercase tracking-wide mb-3">Contents</p>
          <ol className="space-y-1.5">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="text-sm text-accent hover:underline">
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="space-y-10">
          {SECTIONS.map((s) => (
            <section key={s.id} id={s.id}>
              <h2 className="text-xl font-bold text-ink-900 mb-3">{s.title}</h2>
              <div className="text-ink-700 text-sm leading-relaxed whitespace-pre-line">{s.content}</div>
            </section>
          ))}
        </div>

        <div className="mt-12 bg-ink-50 rounded-2xl p-6 border border-ink-100">
          <p className="text-accent font-medium mb-1">Questions about your data?</p>
          <p className="text-accent text-sm">
            Email our DPO:{" "}
            <a href="mailto:privacy@hireschema.com" className="underline font-semibold">
              privacy@hireschema.com
            </a>
            {" "}· We respond within 72 hours.
          </p>
          <p className="text-micro text-ink-500 mt-4">
            <Link href="/terms" className="text-accent hover:underline">
              Terms of Service
            </Link>
            {" · "}
            <Link href="/signup" className="text-accent hover:underline">
              Back to Hireschema
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
