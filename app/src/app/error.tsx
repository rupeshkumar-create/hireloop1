"use client";

import { useEffect } from "react";

/**
 * Route-level error boundary. Catches render/data errors in any page and shows a
 * recoverable screen with a "Try again" (reset) instead of a blank crash.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[app:error-boundary]", error);
  }, [error]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-paper-1 px-6">
      <div className="text-center max-w-md">
        <p className="text-micro font-medium uppercase tracking-wide text-ink-500">
          Something went wrong
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-ink-900">
          That didn’t load as expected
        </h1>
        <p className="mt-2 text-small text-ink-500">
          A temporary hiccup on our side. You can retry, or head back to your dashboard.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center rounded-md bg-ink-900 px-4 py-2 text-small font-medium text-paper-0 hover:bg-ink-700 transition-colors"
          >
            Try again
          </button>
          <a
            href="/dashboard"
            className="inline-flex items-center rounded-md border border-ink-200 px-4 py-2 text-small font-medium text-ink-700 hover:bg-ink-50 transition-colors"
          >
            Go to dashboard
          </a>
        </div>
        {error?.digest && (
          <p className="mt-4 text-micro text-ink-300">Reference: {error.digest}</p>
        )}
      </div>
    </main>
  );
}
