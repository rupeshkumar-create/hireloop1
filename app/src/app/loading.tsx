/**
 * Route-level loading fallback — shown during full route transitions before a
 * page's own data/skeletons take over. Keeps navigation from flashing a blank
 * screen. Individual panels still render their own finer-grained skeletons.
 */
export default function Loading() {
  return (
    <div
      className="min-h-screen flex items-center justify-center bg-paper-1"
      role="status"
      aria-live="polite"
    >
      <div className="flex flex-col items-center gap-3">
        <span
          className="h-6 w-6 rounded-full border-2 border-ink-200 border-t-ink-900 animate-spin"
          aria-hidden
        />
        <span className="sr-only">Loading…</span>
      </div>
    </div>
  );
}
