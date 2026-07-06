import type { ChatStreamCallbacks, ChatStreamPayload } from "@/lib/chat/types";

const DEFAULT_IDLE_TIMEOUT_MS = 90_000;

export type ConsumeSSEOptions = {
  signal?: AbortSignal;
  idleTimeoutMs?: number;
  callbacks?: ChatStreamCallbacks;
};

export type ConsumeSSEResult = {
  text: string;
  error: string | null;
  sawDone: boolean;
};

/** Parse a Hireloop text/event-stream response body (Aarya, Nitya, public portfolio). */
export async function consumeSSEStream(
  body: ReadableStream<Uint8Array>,
  options: ConsumeSSEOptions = {},
): Promise<ConsumeSSEResult> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const idleTimeoutMs = options.idleTimeoutMs ?? DEFAULT_IDLE_TIMEOUT_MS;
  const callbacks = options.callbacks ?? {};

  let accumulated = "";
  let streamError: string | null = null;
  let sawDone = false;
  let buffer = "";

  const readNextChunk = async (): Promise<ReadableStreamReadResult<Uint8Array>> => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    try {
      return await Promise.race([
        reader.read(),
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => {
            reject(new Error("Response timed out. Please try again."));
          }, idleTimeoutMs);
        }),
      ]);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  };

  const consumeFrames = () => {
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const data = line.slice(5).replace(/^ /, "");

      if (data === "[DONE]") {
        sawDone = true;
        callbacks.onDone?.();
        continue;
      }

      try {
        const parsed = JSON.parse(data) as ChatStreamPayload;
        if (parsed.error) {
          streamError = parsed.error;
          callbacks.onError?.(parsed.error);
          continue;
        }
        if (parsed.status) {
          callbacks.onStatus?.(parsed.status);
        }
        if (Array.isArray(parsed.chips) && parsed.chips.length > 0) {
          callbacks.onChips?.(parsed.chips);
        }
        if (Array.isArray(parsed.jobs) && parsed.jobs.length > 0) {
          callbacks.onJobs?.(parsed.jobs);
        }
        if (parsed.text) {
          accumulated += parsed.text;
          callbacks.onText?.(parsed.text, accumulated);
        }
      } catch {
        /* ignore partial frames */
      }
    }
  };

  try {
    while (true) {
      if (options.signal?.aborted) {
        await reader.cancel().catch(() => undefined);
        break;
      }
      const { done, value } = await readNextChunk();
      if (value) {
        buffer += decoder.decode(value, { stream: true });
        consumeFrames();
      }
      if (done) {
        buffer += decoder.decode();
        consumeFrames();
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }

  return { text: accumulated, error: streamError, sawDone };
}
