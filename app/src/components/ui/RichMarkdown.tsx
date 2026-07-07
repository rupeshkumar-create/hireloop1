"use client";

/**
 * Lightweight markdown → rich text. Used in chat bubbles and application-kit docs.
 */

import { cn } from "@/lib/utils";

type RichMarkdownProps = {
  content: string;
  variant?: "chat" | "document";
  className?: string;
};

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const regex = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(_[^_\n]+_)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("`")) {
      nodes.push(
        <code
          key={key++}
          className="rounded-sm bg-ink-50 px-1.5 py-0.5 font-mono text-[0.85em] text-ink-900 ring-1 ring-ink-100"
        >
          {tok.slice(1, -1)}
        </code>,
      );
    } else if (tok.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold text-ink-900">
          {tok.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(
        <em key={key++} className="italic text-ink-600">
          {tok.slice(1, -1)}
        </em>,
      );
    }
    last = regex.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function headingClass(level: number, variant: "chat" | "document"): string {
  if (variant === "document") {
    if (level === 1) {
      return "text-h2 font-semibold text-ink-900 tracking-tight";
    }
    if (level === 2) {
      return "text-h3 font-semibold text-ink-900 border-b border-accent/35 pb-2";
    }
    return "text-small font-semibold uppercase tracking-wide text-accent";
  }
  return "font-semibold text-ink-900 pt-0.5";
}

export function RichMarkdown({
  content,
  variant = "chat",
  className,
}: RichMarkdownProps) {
  const lines = content.split("\n");
  const isDocument = variant === "document";

  return (
    <div
      className={cn(
        isDocument
          ? "space-y-3 text-small leading-relaxed text-ink-700"
          : "space-y-1.5 text-body leading-relaxed text-ink-900",
        className,
      )}
    >
      {lines.map((line, i) => {
        const trimmed = line.trimStart();

        const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
        if (heading) {
          const level = heading[1].length;
          return (
            <p
              key={i}
              className={cn(
                headingClass(level, variant),
                isDocument && level === 2 && i > 0 && "mt-6",
              )}
            >
              {renderInline(heading[2])}
            </p>
          );
        }

        const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
        if (bullet) {
          if (isDocument) {
            return (
              <div
                key={i}
                className="flex gap-3 rounded-lg border border-ink-100 bg-paper-0/60 px-3.5 py-3 shadow-1"
              >
                <span
                  className="mt-2 h-2 w-2 shrink-0 rounded-full bg-accent ring-2 ring-accent/25"
                  aria-hidden
                />
                <p className="min-w-0 flex-1">{renderInline(bullet[1])}</p>
              </div>
            );
          }
          return (
            <div key={i} className="flex items-start gap-2.5">
              <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-ink-400" />
              <span>{renderInline(bullet[1])}</span>
            </div>
          );
        }

        const numbered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
        if (numbered) {
          if (isDocument) {
            return (
              <div
                key={i}
                className="flex gap-3 rounded-lg border border-ink-100 bg-paper-0/60 px-3.5 py-3"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center bg-accent text-micro font-bold text-on-accent">
                  {numbered[1]}
                </span>
                <p className="min-w-0 flex-1 pt-0.5">{renderInline(numbered[2])}</p>
              </div>
            );
          }
          return (
            <div key={i} className="flex items-start gap-2.5">
              <span className="mt-px min-w-[1.1em] shrink-0 text-small font-medium text-ink-500">
                {numbered[1]}.
              </span>
              <span>{renderInline(numbered[2])}</span>
            </div>
          );
        }

        if (trimmed === "") {
          return <div key={i} className={isDocument ? "h-2" : "h-1.5"} aria-hidden />;
        }

        return (
          <p key={i} className={isDocument ? "text-ink-700" : undefined}>
            {renderInline(line)}
          </p>
        );
      })}
    </div>
  );
}
