export default function MatchesLoading() {
  return (
    <div className="min-h-screen bg-paper-0 p-6 space-y-4">
      <div className="h-8 w-56 rounded bg-ink-50 animate-pulse" />
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-40 rounded-xl bg-ink-50 animate-pulse" />
        ))}
      </div>
    </div>
  );
}
