import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { BTN_GHOST, BTN_PRIMARY } from "@/lib/button-classes";
import { cn } from "@/lib/utils";

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
            className={cn(BTN_PRIMARY, "px-4 py-2 text-small")}
          >
            {primaryLabel}
          </Link>
          <Link
            href={user ? "/dashboard" : "/"}
            className={cn(BTN_GHOST, "px-4 py-2 text-small")}
          >
            {user ? "Home" : "App home"}
          </Link>
        </div>
      </div>
    </main>
  );
}
