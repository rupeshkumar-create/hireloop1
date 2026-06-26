export default function DashboardLoading() {
  return (
    <div className="flex h-screen flex-col bg-paper-0">
      <div className="h-14 border-b border-ink-100 bg-paper-0 animate-pulse" />
      <div className="flex flex-1 gap-4 p-4">
        <div className="hidden lg:block w-1/2 rounded-xl bg-ink-50 animate-pulse" />
        <div className="flex-1 rounded-xl bg-ink-50 animate-pulse" />
      </div>
    </div>
  );
}
