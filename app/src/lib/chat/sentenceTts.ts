/**
 * Sentence-boundary helpers for streaming TTS during SSE replies.
 */

const SENTENCE_END = /[.?!](?:\s|$)/;

/** Completed sentences in `text` that are not yet in `alreadySpoken`. */
export function extractNewCompleteSentences(
  alreadySpoken: string,
  fullText: string
): string[] {
  const trimmed = fullText.trim();
  if (!trimmed || trimmed.length <= alreadySpoken.length) return [];

  const delta = trimmed.slice(alreadySpoken.length).trimStart();
  if (!delta) return [];

  const sentences: string[] = [];
  let buf = "";
  for (const ch of delta) {
    buf += ch;
    if (SENTENCE_END.test(buf)) {
      const s = buf.trim();
      if (s.length > 2) sentences.push(s);
      buf = "";
    }
  }
  return sentences;
}

/** Tail not yet spoken (incomplete last sentence). */
export function remainingSpeechTail(alreadySpoken: string, fullText: string): string {
  const trimmed = fullText.trim();
  if (!trimmed) return "";
  if (trimmed.length <= alreadySpoken.length) return trimmed;

  const spokenPrefix = trimmed.slice(0, alreadySpoken.length);
  const delta = trimmed.slice(alreadySpoken.length).trimStart();
  if (!delta) return "";

  // If we spoke complete sentences, `alreadySpoken` may not match exact prefix — find tail.
  if (!trimmed.startsWith(spokenPrefix.trim())) {
    const lastEnd = Math.max(
      trimmed.lastIndexOf(". "),
      trimmed.lastIndexOf("? "),
      trimmed.lastIndexOf("! ")
    );
    if (lastEnd >= 0 && lastEnd + 2 <= trimmed.length) {
      return trimmed.slice(lastEnd + 2).trim();
    }
    return delta;
  }
  return delta;
}
