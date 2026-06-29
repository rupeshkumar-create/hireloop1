import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { BLOG_POSTS } from "@/lib/blog-posts";

export const metadata: Metadata = {
  title: "Blog — AI Recruiting Insights for India",
  description:
    "Hiring trends, career advice, and product updates from the Hireloop team. Built for the Indian job market.",
};

const TAG_COLORS: Record<string, "brand" | "accent" | "muted" | "success"> = {
  Insights: "brand",
  Compliance: "success",
  Tech: "accent",
  Market: "muted",
};

export default function BlogPage() {
  return (
    <main>
      <section className="border-b border-ink-100 bg-ink-900 py-16">
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
            {BLOG_POSTS.map((post) => (
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
