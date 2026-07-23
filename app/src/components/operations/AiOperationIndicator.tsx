"use client";

import { useMemo } from "react";

import { useAiOperations } from "@/components/providers/AiOperationsProvider";
import { isTerminalAiOperationStatus } from "@/lib/operations/polling";

import { AiOperationProgress } from "./AiOperationProgress";

/**
 * Global strip of active (and recently failed/cancelled) AI work.
 * Safe fields only — never exposes queue payloads.
 */
export function AiOperationIndicator() {
  const { operations, cancelOperation, retryOperation } = useAiOperations();

  const visible = useMemo(() => {
    const rows = Object.values(operations);
    const active = rows.filter((op) => !isTerminalAiOperationStatus(op.status));
    if (active.length > 0) return active;

    // After reload/recovery, briefly surface the latest terminal failure so
    // retry remains reachable until the user dismisses via navigation.
    const failedRetryable = rows
      .filter((op) => op.status === "failed" && op.retryable)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    return failedRetryable.slice(0, 1);
  }, [operations]);

  if (visible.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(100vw-2rem,22rem)] flex-col gap-2"
      data-testid="ai-operation-indicator"
    >
      {visible.map((operation) => (
        <div key={operation.id} className="pointer-events-auto shadow-md">
          <AiOperationProgress
            operation={operation}
            onCancel={
              !isTerminalAiOperationStatus(operation.status)
                ? () => {
                    void cancelOperation(operation.id).catch(() => undefined);
                  }
                : undefined
            }
            onRetry={
              operation.status === "failed" && operation.retryable
                ? () => {
                    void retryOperation(operation.id).catch(() => undefined);
                  }
                : undefined
            }
          />
        </div>
      ))}
    </div>
  );
}
