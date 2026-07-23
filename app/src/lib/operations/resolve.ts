/**
 * Shared helpers for resolving durable AI generation submissions in feature UIs.
 * API modules return ReadyOrAccepted; callers track via the provider.
 */

import type {
  AiOperationAccepted,
  AiOperationResponse,
} from "@/lib/api/aiOperations";
import type { ReadyOrAccepted } from "@/lib/api/aiOperations";
import type { TrackOperationOptions } from "@/lib/operations/kinds";
import { isTerminalAiOperationStatus } from "@/lib/operations/polling";

export async function resolveReadyOrAccepted<T>(
  outcome: ReadyOrAccepted<T>,
  trackAndWait: (
    accepted: AiOperationAccepted,
    options?: TrackOperationOptions,
  ) => Promise<AiOperationResponse>,
  fetchWhenReady: () => Promise<T>,
  options?: TrackOperationOptions,
): Promise<T> {
  if (outcome.status === "ready") return outcome.data;
  const terminal = await trackAndWait(outcome.operation, options);
  if (terminal.status !== "succeeded") {
    throw new Error(
      terminal.error_message?.trim() ||
        terminal.message.trim() ||
        "Generation did not complete.",
    );
  }
  return fetchWhenReady();
}

/**
 * After retryOperation returns a replacement, wait until that op is terminal.
 * Does not re-submit the feature endpoint.
 */
export async function waitForTrackedOperation(
  operation: AiOperationResponse,
  waitForOperation: (operationId: string) => Promise<AiOperationResponse>,
): Promise<AiOperationResponse> {
  if (isTerminalAiOperationStatus(operation.status)) {
    return operation;
  }
  return waitForOperation(operation.id);
}

export function terminalOperationError(operation: AiOperationResponse): Error {
  return new Error(
    operation.error_message?.trim() ||
      operation.message.trim() ||
      (operation.status === "cancelled"
        ? "Cancelled."
        : "Something went wrong. Try again."),
  );
}
