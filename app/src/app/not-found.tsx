import Link from "next/link";

/** Friendly 404 — replaces Next.js's bare default for unknown URLs. */
export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-paper-1 px-6">
      <div className="text-center max-w-md">
        <p className="text-micro font-medium uppercase tracking-wide text-ink-500">
          Error 404
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-ink-900">
          We couldn’t find that page
        </h1>
        <p className="mt-2 text-small text-ink-500">
          The link may be broken or the page may have moved. Let’s get you back on track.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Link
            href="/dashboard"
            className="inline-flex items-center rounded-md bg-ink-900 px-4 py-2 text-small font-medium text-paper-0 hover:bg-ink-700 transition-colors"
          >
            Go to dashboard
          </Link>
          <Link
            href="/"
            className="inline-flex items-center rounded-md border border-ink-200 px-4 py-2 text-small font-medium text-ink-700 hover:bg-ink-50 transition-colors"
          >
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}
