export type RetryNotice = {
  attempt: number;
  delayMs: number;
};

type RetryOptions = {
  attempts?: number;
  delaysMs?: readonly number[];
  onRetry?: (notice: RetryNotice) => void;
  sleep?: (delayMs: number) => Promise<void>;
};

const TRANSIENT_STATUSES = new Set([502, 503, 504]);

function isTransientError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return ["ApiUnreachableError", "AbortError", "TimeoutError", "TypeError"].includes(
    error.name,
  );
}

function isTransientResult(result: unknown): boolean {
  if (!result || typeof result !== "object" || !("status" in result)) return false;
  return TRANSIENT_STATUSES.has(Number((result as { status: unknown }).status));
}

function defaultSleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, delayMs));
}

/** Retry only short-lived connectivity/gateway failures, never auth or validation. */
export async function withTransientRetry<T>(
  operation: (attempt: number) => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const attempts = options.attempts ?? 3;
  const delaysMs = options.delaysMs ?? [350, 900];
  const sleep = options.sleep ?? defaultSleep;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const result = await operation(attempt);
      if (!isTransientResult(result) || attempt === attempts) return result;
    } catch (error) {
      if (!isTransientError(error) || attempt === attempts) throw error;
    }

    const delayMs = delaysMs[Math.min(attempt - 1, delaysMs.length - 1)] ?? 0;
    options.onRetry?.({ attempt, delayMs });
    await sleep(delayMs);
  }

  throw new Error("Retry loop exhausted unexpectedly.");
}
