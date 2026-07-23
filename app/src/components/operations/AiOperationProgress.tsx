"use client";

import { Button } from "@/components/ui";
import type { AiOperationResponse } from "@/lib/api/aiOperations";
import { isTerminalAiOperationStatus } from "@/lib/operations/polling";
import { cn } from "@/lib/utils";

function stageLabel(stage: string): string {
  const trimmed = stage.trim();
  if (!trimmed) return "Working";
  return trimmed
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function safeMessage(operation: AiOperationResponse): string {
  if (operation.status === "failed") {
    return (
      operation.error_message?.trim() ||
      operation.message.trim() ||
      "Something went wrong. Try again."
    );
  }
  if (operation.status === "cancelled") {
    return operation.message.trim() || "Cancelled.";
  }
  if (operation.status === "succeeded") {
    return operation.message.trim() || "Ready.";
  }
  return operation.message.trim() || "Working on your request…";
}

export type AiOperationProgressProps = {
  operation: AiOperationResponse;
  onCancel?: () => void;
  onRetry?: () => void;
  className?: string;
  /** Compact single-line layout for inline feature panels. */
  compact?: boolean;
};

/**
 * Safe progress UI for one AI operation.
 * Never renders queue payloads, prompts, or raw provider errors.
 */
export function AiOperationProgress({
  operation,
  onCancel,
  onRetry,
  className,
  compact = false,
}: AiOperationProgressProps) {
  const active = !isTerminalAiOperationStatus(operation.status);
  const showCancel = active && Boolean(onCancel);
  const showRetry =
    operation.status === "failed" && operation.retryable && Boolean(onRetry);
  const percent = Math.max(0, Math.min(100, operation.progress_percent));
  const label = stageLabel(operation.stage);
  const message = safeMessage(operation);

  return (
    <div
      className={cn(
        "rounded-md border border-ink-100 bg-paper-1 p-3",
        compact && "p-2",
        className,
      )}
      role="status"
      aria-live="polite"
      data-operation-id={operation.id}
      data-operation-status={operation.status}
    >
      <div className={cn("flex items-start justify-between gap-3", compact && "gap-2")}>
        <div className="min-w-0 space-y-1">
          <p className="text-small font-medium text-ink-900">{label}</p>
          <p className="text-micro text-ink-500">{message}</p>
        </div>
        {(showCancel || showRetry) && (
          <div className="flex shrink-0 items-center gap-2">
            {showCancel ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onCancel}
                aria-label="Cancel generation"
              >
                Cancel
              </Button>
            ) : null}
            {showRetry ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onRetry}
                aria-label="Retry generation"
              >
                Retry
              </Button>
            ) : null}
          </div>
        )}
      </div>
      {active || operation.status === "succeeded" ? (
        <div className="mt-2">
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-label={`${label} progress`}
            className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100"
          >
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-300",
                operation.status === "succeeded" ? "bg-accent" : "bg-ink-900",
              )}
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="mt-1 text-micro text-ink-500">{percent}%</p>
        </div>
      ) : null}
    </div>
  );
}
