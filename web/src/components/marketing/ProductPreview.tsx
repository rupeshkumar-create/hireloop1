import { cn } from "@/lib/utils";

type ProductPreviewProps = {
  variant?: "candidate" | "recruiter";
  className?: string;
};

export function ProductPreview({ variant = "candidate", className }: ProductPreviewProps) {
  const isCandidate = variant === "candidate";

  return (
    <div
      className={cn(
        "relative mx-auto w-full max-w-3xl rounded-xl border border-ink-200 bg-paper-1 shadow-2 overflow-hidden",
        className,
      )}
      aria-hidden
    >
      <div className="flex items-center gap-2 border-b border-ink-100 bg-ink-50 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-ink-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-ink-300" />
        <span className="h-2.5 w-2.5 rounded-full bg-ink-300" />
        <span className="ml-2 text-micro text-ink-400">
          {isCandidate ? "hireschema.com/dashboard" : "hireschema.com/recruiter"}
        </span>
      </div>

      <div className="flex min-h-[280px]">
        {isCandidate ? (
          <>
            <div className="hidden sm:flex w-[38%] border-r border-ink-100 bg-paper-0 p-4 flex-col gap-3">
              <div className="h-3 w-20 rounded bg-ink-100" />
              <div className="rounded-lg border border-ink-100 p-3 space-y-2">
                <div className="h-2.5 w-3/4 rounded bg-accent/30" />
                <div className="h-2 w-full rounded bg-ink-100" />
                <div className="h-2 w-5/6 rounded bg-ink-100" />
              </div>
              <div className="rounded-lg border border-ink-100 p-3 space-y-2">
                <div className="flex gap-2">
                  <div className="h-8 w-8 rounded-full bg-ink-100 shrink-0" />
                  <div className="flex-1 space-y-1.5 pt-1">
                    <div className="h-2 w-full rounded bg-ink-100" />
                    <div className="h-2 w-2/3 rounded bg-ink-100" />
                  </div>
                  <div className="h-5 w-8 rounded-full bg-accent/20" />
                </div>
              </div>
            </div>
            <div className="flex-1 bg-paper-1 p-4 flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-ink-900" />
                <div className="h-2.5 w-16 rounded bg-ink-100" />
              </div>
              <div className="rounded-lg bg-ink-50 border border-ink-100 p-3 max-w-[85%]">
                <div className="h-2 w-full rounded bg-ink-200 mb-1.5" />
                <div className="h-2 w-4/5 rounded bg-ink-200" />
              </div>
              <div className="rounded-lg bg-accent/10 border border-accent/20 p-3 max-w-[75%] ml-auto">
                <div className="h-2 w-full rounded bg-accent/30 mb-1.5" />
                <div className="h-2 w-2/3 rounded bg-accent/20" />
              </div>
              <div className="mt-auto h-9 rounded-lg border border-ink-200 bg-paper-0" />
            </div>
          </>
        ) : (
          <>
            <div className="hidden sm:flex w-14 border-r border-ink-100 bg-paper-0 flex-col items-center py-3 gap-2">
              <div className="h-9 w-9 rounded-xl bg-ink-900" />
              <div className="h-8 w-8 rounded-lg bg-ink-900/10" />
              <div className="h-8 w-8 rounded-lg bg-ink-100" />
            </div>
            <div className="flex-1 p-4 space-y-3">
              <div className="h-3 w-24 rounded bg-ink-100" />
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg border border-ink-100 p-3"
                >
                  <div className="h-10 w-10 rounded-full bg-ink-100 shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-2.5 w-1/2 rounded bg-ink-100" />
                    <div className="h-2 w-3/4 rounded bg-ink-100" />
                  </div>
                  <div className="h-6 w-12 rounded-full bg-accent/20" />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
