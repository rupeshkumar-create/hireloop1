import type { Metadata } from "next";
import Link from "next/link";

import { allJobSlugs, jobFaqs, parseJobSlug, titleCase } from "@/lib/programmatic";

const BASE_URL = "https://hireloop.in";

type PageProps = { params: Promise<{ slug: string }> };

export async function generateStaticParams() {
  return allJobSlugs().map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const parsed = parseJobSlug(slug);
  if (!parsed) return { title: "Jobs in India | Hireloop" };
  const roleLabel = titleCase(parsed.role);
  const cityLabel = titleCase(parsed.city);
  const title = `${roleLabel} Jobs in ${cityLabel} | Hireloop`;
  const description = `Find ${roleLabel} roles in ${cityLabel}, India. AI-matched jobs in INR, warm intros to hiring managers, and a résumé tailored to each JD.`;
  const canonical = `${BASE_URL}/jobs/${slug}`;
  return {
    title,
    description,
    alternates: { canonical },
    openGraph: { title, description, url: canonical, type: "website" },
  };
}

export default async function ProgrammaticJobPage({ params }: PageProps) {
  const { slug } = await params;
  const parsed = parseJobSlug(slug);
  if (!parsed) {
    return (
      <main className="p-8">
        <p>Page not found.</p>
        <Link href="/">Home</Link>
      </main>
    );
  }

  const roleLabel = titleCase(parsed.role);
  const cityLabel = titleCase(parsed.city);
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://app.hireloop.in";
  const canonical = `${BASE_URL}/jobs/${slug}`;
  const faqs = jobFaqs(roleLabel, cityLabel);

  // Structured data: helps Google rich results + AI answer engines cite the page.
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "CollectionPage",
        "@id": canonical,
        url: canonical,
        name: `${roleLabel} Jobs in ${cityLabel}`,
        description: `AI-matched ${roleLabel} roles in ${cityLabel}, India on Hireloop.`,
        isPartOf: { "@type": "WebSite", name: "Hireloop", url: BASE_URL },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: BASE_URL },
          { "@type": "ListItem", position: 2, name: "Jobs", item: `${BASE_URL}/jobs` },
          { "@type": "ListItem", position: 3, name: `${roleLabel} in ${cityLabel}`, item: canonical },
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: faqs.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
    ],
  };

  return (
    <main className="max-w-3xl mx-auto px-6 py-16">
      <script
        type="application/ld+json"
        // Escape `<` (and `&`) so job-supplied text containing "</script>" can't
        // break out of the JSON-LD block — XSS-safe serialization.
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jsonLd)
            .replace(/</g, "\\u003c")
            .replace(/&/g, "\\u0026"),
        }}
      />

      <nav className="text-sm text-ink-500" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-ink-900">
          Home
        </Link>{" "}
        / <Link href="/jobs" className="hover:text-ink-900">Jobs</Link> /{" "}
        <span className="text-ink-700">
          {roleLabel} in {cityLabel}
        </span>
      </nav>

      <h1 className="mt-4 text-3xl font-bold text-ink-900">
        {roleLabel} jobs in {cityLabel}
      </h1>
      <p className="mt-4 text-ink-700">
        Hireloop surfaces India-only {roleLabel} openings in {cityLabel} with AI match scores,
        direct apply links, and warm intros to hiring managers — salaries in INR, no spam.
      </p>

      <section className="mt-8 rounded-2xl border bg-ink-50 p-6">
        <h2 className="font-semibold">Why candidates use Hireloop</h2>
        <ul className="mt-3 list-disc list-inside text-sm text-ink-700 space-y-1">
          <li>Daily ranked matches (India geo-lock, INR salaries)</li>
          <li>Request Intro — email from your Gmail, not spam</li>
          <li>Tailored résumé per JD in under 30 seconds</li>
        </ul>
      </section>

      <div className="mt-10 flex gap-4">
        <a
          href={`${appUrl}/signup`}
          className="inline-flex bg-accent text-paper-0 px-6 py-3 rounded-xl font-medium"
        >
          Get matched free
        </a>
        <Link href="/candidates" className="inline-flex text-accent px-4 py-3">
          How it works
        </Link>
      </div>

      <section className="mt-14">
        <h2 className="text-xl font-semibold text-ink-900">
          {roleLabel} jobs in {cityLabel} — FAQs
        </h2>
        <dl className="mt-4 space-y-5">
          {faqs.map((f) => (
            <div key={f.q}>
              <dt className="font-medium text-ink-900">{f.q}</dt>
              <dd className="mt-1 text-sm text-ink-700">{f.a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </main>
  );
}
