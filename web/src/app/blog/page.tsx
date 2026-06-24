import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";

export const metadata: Metadata = {
  title: "Blog — AI Recruiting Insights for India",
  description:
    "Hiring trends, career advice, and product updates from the Hireloop team. Built for the Indian job market.",
};

// Placeholder posts — will be replaced with CMS/MDX in P24
const POSTS = [
  {
    slug: "warm-intro-vs-cold-apply",
    title: "Why a warm intro beats a cold apply — every time",
    excerpt:
      "An email from the candidate's own Gmail gets a 3× higher reply rate than recruiter outreach. Here's the data behind the mechanic that powers Hireloop.",
    tag: "Insights",
    date: "2026-01-15",
    readMins: 5,
  },
  {
    slug: "dpdp-act-2023-hiring",
    title: "What the DPDP Act 2023 means for hiring in India",
    excerpt:
      "Consent logs, bias audits, and right-to-delete aren't optional any more. Here's how Hireloop builds compliance into its core data model.",
    tag: "Compliance",
    date: "2026-01-08",
    readMins: 7,
  },
  {
    slug: "apify-vs-apollo-india",
    title: "Apify vs Apollo/Lusha for Indian HM enrichment — a cost breakdown",
    excerpt:
      "Apollo costs ₹40–100 per contact. Apify's waterfall costs ₹9–13 with the same or better quality. Here's the full comparison.",
    tag: "Tech",
    date: "2025-12-20",
    readMins: 6,
  },
  {
    slug: "india-ai-recruiting-2026",
    title: "The state of AI recruiting in India — 2026 edition",
    excerpt:
      "From keyword-matching job boards to semantic AI agents. Where the market is headed, and why the warm intro mechanic changes everything.",
    tag: "Market",
    date: "2025-12-10",
    readMins: 8,
  },
];

const TAG_COLORS: Record<string, "brand" | "accent" | "muted" | "success"> = {
  Insights: "brand",
  Compliance: "success",
  Tech: "accent",
  Market: "muted",
};

export default function BlogPage() {
  return (
    <main>
      <section className="border-b border-ink-100 bg-paper-0">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h1 className="text-5xl font-bold text-paper-0 mb-4">Blog</h1>
          <p className="text-ink-300 text-lg">
            AI recruiting insights, product updates, and the India hiring market.
          </p>
        </div>
      </section>

      <section className="py-16 bg-paper-1">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <div className="grid gap-6">
            {POSTS.map((post) => (
              <article
                key={post.slug}
                className="bg-ink-50 rounded-2xl p-6 hover:shadow-md transition-shadow"
              >
                <div className="flex items-center gap-3 mb-3">
                  <Badge variant={TAG_COLORS[post.tag] ?? "muted"}>{post.tag}</Badge>
                  <span className="text-xs text-ink-500">
                    {new Date(post.date).toLocaleDateString("en-IN", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </span>
                  <span className="text-xs text-ink-500">· {post.readMins} min read</span>
                </div>
                <h2 className="text-xl font-bold text-ink-900 mb-2 hover:text-accent transition-colors">
                  <Link href={`/blog/${post.slug}`}>{post.title}</Link>
                </h2>
                <p className="text-sm text-ink-500 leading-relaxed mb-4">{post.excerpt}</p>
                <Link
                  href={`/blog/${post.slug}`}
                  className="text-sm font-medium text-accent hover:text-accent transition-colors"
                >
                  Read more →
                </Link>
              </article>
            ))}
          </div>

          <div className="mt-12 bg-ink-50 rounded-2xl p-6 text-center border border-ink-100">
            <p className="text-accent font-medium mb-2">More posts coming soon</p>
            <p className="text-ink-900 text-sm">
              Subscribe to our newsletter for weekly AI recruiting insights.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
