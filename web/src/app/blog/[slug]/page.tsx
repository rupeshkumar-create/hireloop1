import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/Badge";
import { BLOG_POSTS, getBlogPost } from "@/lib/blog-posts";

type Props = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return BLOG_POSTS.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const post = getBlogPost(slug);
  if (!post) return { title: "Post not found" };
  return {
    title: post.title,
    description: post.excerpt,
  };
}

export default async function BlogPostPage({ params }: Props) {
  const { slug } = await params;
  const post = getBlogPost(slug);
  if (!post) notFound();

  return (
    <main className="bg-paper-1 min-h-screen">
      <article className="max-w-2xl mx-auto px-4 sm:px-6 py-12">
        <Link
          href="/blog"
          className="text-small text-ink-500 hover:text-ink-900 transition-colors"
        >
          ← Back to blog
        </Link>
        <div className="mt-6 flex items-center gap-3">
          <Badge variant="muted">{post.tag}</Badge>
          <span className="text-micro text-ink-500">
            {new Date(post.date).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
            {" · "}
            {post.readMins} min read
          </span>
        </div>
        <h1 className="mt-4 text-h1 font-semibold text-ink-900 leading-tight">
          {post.title}
        </h1>
        <p className="mt-4 text-body text-ink-600 leading-relaxed">{post.excerpt}</p>
        <div className="mt-8 space-y-4 text-body text-ink-700 leading-relaxed">
          {post.body.map((para) => (
            <p key={para.slice(0, 24)}>{para}</p>
          ))}
        </div>
      </article>
    </main>
  );
}
