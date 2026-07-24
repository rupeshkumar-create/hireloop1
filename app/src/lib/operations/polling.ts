import type { AiOperationStatus } from "@/lib/api/aiOperations";

/** After this age, running work backs off from 3s to 5s polling. */
export const SUSTAINED_WORK_MS = 30_000;

const TERMINAL_STATUSES = new Set<AiOperationStatus>([
  "succeeded",
  "failed",
  "cancelled",
]);

export type AiOperationPollingInput = {
  status: AiOperationStatus;
  createdAt: Date | string;
  now?: Date | string;
  visibilityState?: DocumentVisibilityState;
};

function toTime(value: Date | string): number {
  return value instanceof Date ? value.getTime() : new Date(value).getTime();
}

/**
 * Adaptive poll interval for durable AI operations.
 * Returns `false` to pause (hidden tab) or stop (terminal status).
 */
export function getAiOperationPollingIntervalMs(
  input: AiOperationPollingInput,
): number | false {
  if (input.visibilityState === "hidden") return false;
  if (TERMINAL_STATUSES.has(input.status)) return false;

  if (input.status === "queued") return 1500;

  const nowMs = toTime(input.now ?? new Date());
  const createdMs = toTime(input.createdAt);
  const ageMs = Number.isFinite(nowMs - createdMs) ? nowMs - createdMs : 0;

  if (ageMs >= SUSTAINED_WORK_MS) return 5000;
  return 3000;
}

export function isTerminalAiOperationStatus(status: AiOperationStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}
