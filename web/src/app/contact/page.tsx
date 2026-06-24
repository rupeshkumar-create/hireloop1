import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Contact",
  description: "Get in touch with the Hireloop team. We're based in India and respond within 24 hours.",
};

const CONTACTS = [
  { label: "General enquiries", email: "hello@hireloop.in", icon: "✉️" },
  { label: "Data Privacy (DPO)", email: "privacy@hireloop.in", icon: "🔒" },
  { label: "Partnerships", email: "partnerships@hireloop.in", icon: "🤝" },
  { label: "Press & media", email: "press@hireloop.in", icon: "📰" },
];

export default function ContactPage() {
  return (
    <main>
      <section className="border-b border-ink-100 bg-paper-0">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <h1 className="text-5xl font-bold text-paper-0 mb-4">Get in touch</h1>
          <p className="text-ink-300 text-lg">
            We&apos;re a small team. We read every email and respond within 24 hours.
          </p>
        </div>
      </section>

      <section className="py-16 bg-paper-1">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 space-y-6">
          {CONTACTS.map((c) => (
            <div key={c.label} className="flex items-center gap-4 bg-ink-50 rounded-2xl p-5">
              <span className="text-2xl">{c.icon}</span>
              <div className="flex-1">
                <p className="text-xs text-ink-500 uppercase tracking-wide font-medium mb-0.5">
                  {c.label}
                </p>
                <a
                  href={`mailto:${c.email}`}
                  className="text-accent font-semibold hover:text-accent transition-colors"
                >
                  {c.email}
                </a>
              </div>
            </div>
          ))}

          <div className="bg-ink-50 rounded-2xl p-6 border border-ink-100">
            <h3 className="font-bold text-ink-900 mb-2">Based in India</h3>
            <p className="text-accent text-sm">
              Hireloop Technology Pvt. Ltd.<br />
              India 🇮🇳
            </p>
            <p className="mt-3 text-xs text-ink-900">
              Registered under the Companies Act 2013 · DPDP Act 2023 compliant
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
