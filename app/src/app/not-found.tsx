import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

/** Friendly 404 — primary CTA depends on auth state. */
export default async function NotFound() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const primaryHref = user ? "/dashboard" : "/signup";
  const primaryLabel = user ? "Go to dashboard" : "Sign up";

  return (
    <main className="min-h-screen flex items-center justify-center bg-paper-1 px-6">
      <div className="text-center max-w-md">
        <p className="text-micro font-medium uppercase tracking-wide text-ink-500">
          Error 404
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-ink-900">
          We couldn&apos;t find that page
        </h1>
        <p className="mt-2 text-small text-ink-500">
          The link may be broken or the page may have moved.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Link
            href={primaryHref}
            className="inline-flex items-center rounded-md bg-accent px-4 py-2 text-small font-medium text-accent-fg hover:bg-accent-hover transition-colors"
          >
            {primaryLabel}
          </Link>
          <Link
            href={user ? "/dashboard" : "/"}
            className="inline-flex items-center rounded-md border border-ink-200 px-4 py-2 text-small font-medium text-ink-700 hover:bg-ink-50 transition-colors"
          >
            {user ? "Home" : "App home"}
          </Link>
        </div>
      </div>
    </main>
  );
}
