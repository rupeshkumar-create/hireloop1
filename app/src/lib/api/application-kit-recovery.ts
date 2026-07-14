import { withTransientRetry } from "./transient-retry.ts";

export const APPLICATION_KIT_CONNECTIVITY_MESSAGE =
  "We had trouble connecting. Your application kit is still being prepared.";

const APPLICATION_KIT_FAILED_MESSAGE =
  "We couldn't finish your application kit. Please retry.";

export type ApplicationKitFailure = {
  kind: "connectivity" | "failed";
  message: string;
};

const CONNECTIVITY_ERROR_NAMES = new Set([
  "ApiUnreachableError",
  "AbortError",
  "TimeoutError",
  "TypeError",
  "ApplicationKitConnectivityError",
]);

type ApplicationKitRetryOptions = {
  attempts?: number;
  delaysMs?: readonly number[];
  onRetry?: (notice: { attempt: number; delayMs: number }) => void;
  sleep?: (delayMs: number) => Promise<void>;
};

export async function retryApplicationKitRequest<T>(
  operation: (attempt: number) => Promise<T>,
  options: ApplicationKitRetryOptions = {},
): Promise<T> {
  return withTransientRetry(operation, options);
}

export function toApplicationKitFailure(error: unknown): ApplicationKitFailure {
  if (
    error instanceof Error &&
    CONNECTIVITY_ERROR_NAMES.has(error.name)
  ) {
    return {
      kind: "connectivity",
      message: APPLICATION_KIT_CONNECTIVITY_MESSAGE,
    };
  }
  return { kind: "failed", message: APPLICATION_KIT_FAILED_MESSAGE };
}

export function createApplicationKitError(error: unknown): Error {
  const failure = toApplicationKitFailure(error);
  const safeError = new Error(failure.message);
  safeError.name =
    failure.kind === "connectivity"
      ? "ApplicationKitConnectivityError"
      : "ApplicationKitError";
  return safeError;
}
