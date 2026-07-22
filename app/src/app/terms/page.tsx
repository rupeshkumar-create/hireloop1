import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service",
  description:
    "Hireschema Terms of Service — governing law India. How you may use the platform.",
  robots: { index: true, follow: true },
};

const SECTIONS = [
  {
    id: "acceptance",
    title: "1. Acceptance of terms",
    content: `By accessing or using Hireschema ("the platform"), you agree to be bound by these Terms of Service ("Terms") and our Privacy Policy. If you do not agree, do not use the platform.

These Terms constitute a binding agreement between you and Hireschema, a company incorporated under the Companies Act 2013, India.`,
  },
  {
    id: "eligibility",
    title: "2. Eligibility",
    content: `Hireschema is available to:
• Residents of India (optional +91 phone; SMS OTP verification when enabled)
• Persons aged 18 or older
• Individuals legally permitted to use recruiting services in their jurisdiction

By verifying your phone number, you confirm you meet these requirements.`,
  },
  {
    id: "accounts",
    title: "3. Your account",
    content: `You are responsible for maintaining the security of your account credentials. Do not share your account with third parties.

You must provide accurate information. Misrepresenting your identity, qualifications, or employment history may result in immediate account termination.

You may create one account per identity. Multiple accounts for the same person are not permitted.`,
  },
  {
    id: "candidate-rules",
    title: "4. Candidate conduct",
    content: `As a candidate on Hireschema, you agree to:

• Only request intros to roles you genuinely intend to pursue
• Not use the intro mechanic for spam, market research, or competitor intelligence
• Not misrepresent your qualifications in your profile or intro emails
• Obtain consent before including any third party's information in your profile
• Keep your profile information current and accurate

We reserve the right to suspend accounts that abuse the intro system (e.g., requesting intros with no intent to respond).`,
  },
  {
    id: "recruiter-rules",
    title: "5. Recruiter conduct",
    content: `As a recruiter on Hireschema, you agree to:

• Only use candidate data for the purpose of evaluating them for legitimate roles
• Not export, sell, or share candidate data outside the Hireschema platform
• Respond to candidate intros within 14 days or decline them
• Comply with all applicable employment laws, including equal opportunity requirements
• Not use Hireschema for bulk data harvesting or competitor intelligence

Violation of these rules may result in account termination and legal action under applicable law.`,
  },
  {
    id: "gmail-oauth",
    title: "6. Google OAuth usage",
    content: `Connecting your Google account is optional. If you connect it, you grant Hireschema the gmail.send and calendar.events scopes. Gmail access allows Aarya to send an intro email only after your explicit approval. Calendar access adds an optional reminder event for an Aarya call you schedule; the call still happens privately inside Hireschema, and we do not create or promise a Google Meet link.

We commit to:
• Never reading your inbox or any received messages
• Never reading your existing calendar contents
• Never sending emails without your explicit approval
• Never requiring Google Calendar to start or schedule an Aarya call
• Revoking access immediately if you disconnect Google in settings
• Not storing email content beyond 30 days

You can revoke Google access at any time from Google Account settings → Third-party apps.`,
  },
  {
    id: "career-discovery",
    title: "7. Aarya career-discovery calls",
    content: `An Aarya career-discovery call is a private 15-minute conversation designed to understand your experience, skills, languages, location, and job preferences.

By default, Hireschema stores the transcript needed to continue the conversation and provide the service, but does not retain an audio recording. Your transcript remains private to your candidate experience. Sharing any call-derived information with a recruiter requires a separate, explicit consent step.

During this phase, Aarya does not automatically change your profile or job preferences from the call. Any proposed facts or preference updates must be reviewed and confirmed by you before they are applied.`,
  },
  {
    id: "intellectual-property",
    title: "8. Intellectual property",
    content: `All platform content, design, code, trademarks, and brand assets are owned by Hireschema. You may not copy, modify, or distribute our content without written permission.

Your profile data, resume, and chat history remain your property. You grant Hireschema a limited licence to process this data solely to provide the service.`,
  },
  {
    id: "limitation",
    title: "9. Limitation of liability",
    content: `Hireschema is a platform that facilitates connections between candidates and recruiters. We do not guarantee employment outcomes, interview results, or hiring decisions.

To the maximum extent permitted by Indian law, Hireschema's liability for any claim is limited to ₹10,000 or the amount you paid us in the prior 12 months, whichever is lower.

We are not liable for third-party actions, hiring manager responses, or outcomes of introductions made through the platform.`,
  },
  {
    id: "termination",
    title: "10. Termination",
    content: `We may suspend or terminate your account if you violate these Terms, engage in fraud or abuse, or for any reason with 7 days notice.

You may delete your account at any time. Upon deletion, your data is soft-deleted and permanently purged after 30 days per our Privacy Policy.`,
  },
  {
    id: "governing-law",
    title: "11. Governing law",
    content: `These Terms are governed by the laws of India. Any disputes will be subject to the exclusive jurisdiction of courts in India.

For consumer complaints under the Consumer Protection Act 2019, you may also approach the National Consumer Disputes Redressal Commission.`,
  },
  {
    id: "contact",
    title: "12. Contact",
    content: `For questions about these Terms: hello@hireschema.com
For data/privacy matters: privacy@hireschema.com

Hireschema, India

Last updated: July 2026`,
  },
];

export default function TermsPage() {
  return (
    <main id="main-content" className="py-16 bg-paper-1 min-h-screen">
      <div className="max-w-3xl mx-auto px-4 sm:px-6">
        <div className="mb-10">
          <h1 className="text-4xl font-bold text-ink-900 mb-2">Terms of Service</h1>
          <p className="text-ink-500 text-sm">Effective: July 2026 · Governing law: India</p>
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
          <p className="text-ink-700 text-sm">
            Questions?{" "}
            <a href="mailto:hello@hireschema.com" className="text-accent underline">
              hello@hireschema.com
            </a>
            {" · Privacy: "}
            <a href="mailto:privacy@hireschema.com" className="text-accent underline">
              privacy@hireschema.com
            </a>
          </p>
          <p className="text-micro text-ink-500 mt-4">
            <Link href="/privacy" className="text-accent hover:underline">
              Privacy Policy
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
