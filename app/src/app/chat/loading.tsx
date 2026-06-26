export default function ChatLoading() {
  return (
    <div className="flex h-screen flex-col bg-paper-0 p-4">
      <div className="h-10 w-48 rounded-lg bg-ink-50 animate-pulse mb-4" />
      <div className="flex-1 rounded-xl bg-ink-50 animate-pulse" />
    </div>
  );
}
