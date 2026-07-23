/**
 * Shared helpers for resolving durable AI generation submissions in feature UIs.
 * API modules return ReadyOrAccepted; callers track via the provider.
 */

import type { AiOperationAccepted, AiOperationResponse } from "@/lib/api/aiOperations";
import type { ReadyOrAccepted } from "@/lib/api/aiOperations";

export async function resolveReadyOrAccepted<T>(
  outcome: ReadyOrAccepted<T>,
  trackAndWait: (accepted: AiOperationAccepted) => Promise<AiOperationResponse>,
  fetchWhenReady: () => Promise<T>,
): Promise<T> {
  if (outcome.status === "ready") return outcome.data;
  const terminal = await trackAndWait(outcome.operation);
  if (terminal.status !== "succeeded") {
    throw new Error(
      terminal.error_message?.trim() ||
        terminal.message.trim() ||
        "Generation did not complete.",
    );
  }
  return fetchWhenReady();
}
