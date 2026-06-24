"use client";

/**
 * Lightweight markdown renderer for assistant chat bubbles.
 * Supports **bold**, *italic*, `code`, headings, and bullet/numbered lists.
 */

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
          className="rounded bg-ink-50 px-1 py-0.5 font-mono text-[0.85em] text-ink-900"
        >
          {tok.slice(1, -1)}
        </code>
      );
    } else if (tok.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold text-ink-900">
          {tok.slice(2, -2)}
        </strong>
      );
    } else {
      nodes.push(
        <em key={key++} className="italic">
          {tok.slice(1, -1)}
        </em>
      );
    }
    last = regex.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function MessageText({
  content,
  isUser,
  isStreaming,
}: {
  content: string;
  isUser: boolean;
  isStreaming?: boolean;
}) {
  if (isUser) {
    return (
      <div className="text-body leading-relaxed whitespace-pre-wrap">
        {content}
      </div>
    );
  }

  const lines = content.split("\n");
  return (
    <div className="space-y-1.5 text-body leading-relaxed text-ink-900">
      {lines.map((line, i) => {
        const trimmed = line.trimStart();

        const heading = trimmed.match(/^(#{1,3})\s+(.*)$/);
        if (heading) {
          return (
            <p key={i} className="font-semibold text-ink-900 pt-0.5">
              {renderInline(heading[2])}
            </p>
          );
        }

        const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
        if (bullet) {
          return (
            <div key={i} className="flex items-start gap-2.5">
              <span className="shrink-0 mt-[7px] h-1.5 w-1.5 rounded-full bg-ink-400" />
              <span>{renderInline(bullet[1])}</span>
            </div>
          );
        }

        const numbered = trimmed.match(/^(\d+)[.)]\s+(.*)$/);
        if (numbered) {
          return (
            <div key={i} className="flex items-start gap-2.5">
              <span className="shrink-0 mt-px min-w-[1.1em] text-small font-medium text-ink-500">
                {numbered[1]}.
              </span>
              <span>{renderInline(numbered[2])}</span>
            </div>
          );
        }

        if (trimmed === "") return <div key={i} className="h-1.5" aria-hidden />;

        return <p key={i}>{renderInline(line)}</p>;
      })}
      {isStreaming && (
        <span className="inline-block h-4 w-0.5 bg-ink-700 ml-0.5 align-middle animate-pulse" />
      )}
    </div>
  );
}
